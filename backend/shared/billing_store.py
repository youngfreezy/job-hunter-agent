# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Persistent storage for billing: users, wallets, and transactions.

Uses sync psycopg for table creation (matches application_store.py pattern)
and provides both sync and async helpers for wallet operations.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import stripe

from backend.shared.config import get_settings
from backend.shared.db import get_connection

logger = logging.getLogger(__name__)

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    wallet_balance DECIMAL(10,2) DEFAULT 0.00,
    free_applications_remaining INT DEFAULT 3,
    is_premium BOOLEAN DEFAULT FALSE,
    stripe_customer_id TEXT UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Backfill: add is_premium column if table already exists
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN IF NOT EXISTS is_premium BOOLEAN DEFAULT FALSE;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Backfill: add stripe_customer_id column if table already exists
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT UNIQUE;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Auto-refill preferences
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_refill_enabled BOOLEAN DEFAULT FALSE;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_refill_threshold DECIMAL(10,2) DEFAULT 5.0;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_refill_pack_id TEXT DEFAULT 'top_up_10';
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Phone / SMS notification preferences
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number TEXT UNIQUE;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN DEFAULT FALSE;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_channel TEXT DEFAULT 'email';
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Email/password auth columns
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider TEXT DEFAULT 'google';
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Free trial: anonymous user flag
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN IF NOT EXISTS is_anonymous BOOLEAN DEFAULT FALSE;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS wallet_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    amount DECIMAL(10,2) NOT NULL,
    balance_after DECIMAL(10,2) NOT NULL,
    type TEXT NOT NULL,
    reference_id TEXT,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wallet_tx_user ON wallet_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_wallet_tx_created ON wallet_transactions(user_id, created_at DESC);
"""


def _connect():
    return get_connection()


async def ensure_billing_tables() -> None:
    """Create users + wallet_transactions tables if they don't exist."""
    try:
        with _connect() as conn:
            conn.execute(_CREATE_TABLES)
            conn.commit()
            logger.info("Billing tables ensured")

            # Sync premium status from PREMIUM_EMAILS env var into DB
            s = get_settings()
            premium_emails = [e.strip().lower() for e in s.PREMIUM_EMAILS.split(",") if e.strip()]
            if premium_emails:
                conn.execute(
                    "UPDATE users SET is_premium = TRUE WHERE LOWER(email) = ANY(%s) AND is_premium = FALSE",
                    (premium_emails,),
                )
                conn.commit()
    except Exception:
        logger.exception("Failed to create billing tables")


def get_or_create_user(email: str) -> Dict[str, Any]:
    """Get or create a user by email. Returns dict with id, email, balance, free_remaining."""
    with _connect() as conn:
        cur = conn.execute(
            "SELECT id, email, wallet_balance, free_applications_remaining, is_premium, name, auth_provider, created_at, notification_channel, phone_number FROM users WHERE email = %s",
            (email,),
        )
        row = cur.fetchone()
        if row:
            return {
                "id": str(row[0]),
                "email": row[1],
                "wallet_balance": float(row[2]),
                "free_applications_remaining": row[3],
                "is_premium": row[4],
                "name": row[5],
                "auth_provider": row[6] or "google",
                "created_at": row[7].isoformat() if row[7] else None,
                "notification_channel": row[8] or "email",
                "phone_number": row[9],
            }

        # Create new user
        user_id = str(uuid.uuid4())

        # Create Stripe customer (non-blocking)
        settings = get_settings()
        stripe_customer_id = None
        if settings.STRIPE_SECRET_KEY:
            try:
                stripe.api_key = settings.STRIPE_SECRET_KEY
                customer = stripe.Customer.create(email=email)
                stripe_customer_id = customer.id
            except Exception as e:
                logger.warning("Failed to create Stripe customer for %s: %s", email, e)

        conn.execute(
            "INSERT INTO users (id, email, stripe_customer_id) VALUES (%s, %s, %s)",
            (user_id, email, stripe_customer_id),
        )
        conn.commit()
        return {
            "id": user_id,
            "email": email,
            "wallet_balance": 0.00,
            "free_applications_remaining": 3,
            "is_premium": False,
        }


def get_stripe_customer_id(user_id: str) -> Optional[str]:
    """Get the Stripe customer ID for a user."""
    with _connect() as conn:
        cur = conn.execute(
            "SELECT stripe_customer_id FROM users WHERE id = %s", (user_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None


def get_wallet(user_id: str) -> Dict[str, Any]:
    """Get wallet balance, free applications remaining, and auto-refill info."""
    with _connect() as conn:
        cur = conn.execute(
            """SELECT wallet_balance, free_applications_remaining,
                      auto_refill_enabled, auto_refill_threshold, auto_refill_pack_id
               FROM users WHERE id = %s""",
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return {"balance": 0.0, "free_remaining": 0,
                    "auto_refill_enabled": False, "auto_refill_threshold": 5.0,
                    "auto_refill_pack_id": "top_up_10", "low_balance": False}
        balance = float(row[0])
        auto_refill_enabled = bool(row[2]) if row[2] is not None else False
        auto_refill_threshold = float(row[3]) if row[3] is not None else 5.0
        auto_refill_pack_id = row[4] or "top_up_10"
        low_balance = auto_refill_enabled and balance < auto_refill_threshold
        return {
            "balance": balance,
            "free_remaining": row[1],
            "auto_refill_enabled": auto_refill_enabled,
            "auto_refill_threshold": auto_refill_threshold,
            "auto_refill_pack_id": auto_refill_pack_id,
            "low_balance": low_balance,
        }


def get_auto_refill_settings(user_id: str) -> Dict[str, Any]:
    """Get auto-refill preferences for a user."""
    with _connect() as conn:
        cur = conn.execute(
            """SELECT auto_refill_enabled, auto_refill_threshold, auto_refill_pack_id
               FROM users WHERE id = %s""",
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return {"enabled": False, "threshold": 5.0, "pack_id": "top_up_10"}
        return {
            "enabled": bool(row[0]) if row[0] is not None else False,
            "threshold": float(row[1]) if row[1] is not None else 5.0,
            "pack_id": row[2] or "top_up_10",
        }


def update_auto_refill_settings(
    user_id: str, enabled: bool, threshold: float, pack_id: str
) -> None:
    """Update auto-refill preferences for a user."""
    with _connect() as conn:
        conn.execute(
            """UPDATE users
               SET auto_refill_enabled = %s,
                   auto_refill_threshold = %s,
                   auto_refill_pack_id = %s
               WHERE id = %s""",
            (enabled, threshold, pack_id, user_id),
        )
        conn.commit()


def credit_wallet(
    user_id: str,
    amount: float,
    tx_type: str,
    reference_id: str = "",
    description: str = "",
) -> Dict[str, Any]:
    """Add funds to a user's wallet. Returns new balance."""
    with _connect() as conn:
        # Update balance
        conn.execute(
            "UPDATE users SET wallet_balance = wallet_balance + %s WHERE id = %s",
            (amount, user_id),
        )
        # Get new balance
        cur = conn.execute(
            "SELECT wallet_balance FROM users WHERE id = %s", (user_id,)
        )
        new_balance = float(cur.fetchone()[0])

        # Record transaction
        conn.execute(
            """INSERT INTO wallet_transactions
               (user_id, amount, balance_after, type, reference_id, description)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, amount, new_balance, tx_type, reference_id, description),
        )
        conn.commit()
        return {"balance": new_balance}


def debit_wallet(
    user_id: str,
    amount: float,
    tx_type: str,
    reference_id: str = "",
    description: str = "",
) -> Dict[str, Any]:
    """Deduct credits from wallet. Returns new balance. Raises if insufficient.

    For application charges (tx_type starting with "application_"):
    - Premium (unlimited) users: record transaction at 0 cost
    - Free applications are consumed first (1 free app per attempt, regardless of amount)
    - Then wallet credits are deducted
    """
    with _connect() as conn:
        # Row-level lock to prevent concurrent double-debit
        cur = conn.execute(
            "SELECT wallet_balance, free_applications_remaining, is_premium FROM users WHERE id = %s FOR UPDATE",
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            raise ValueError(f"User {user_id} not found")

        balance = float(row[0])
        free_remaining = row[1]
        is_premium = row[2]

        # Premium users: no debit, just log the transaction
        is_app_charge = tx_type.startswith("application_")
        if is_app_charge and is_premium:
            conn.execute(
                """INSERT INTO wallet_transactions
                   (user_id, amount, balance_after, type, reference_id, description)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (user_id, 0.0, balance, "unlimited_application", reference_id,
                 f"Unlimited plan — {description}" if description else "Unlimited plan application"),
            )
            conn.commit()
            return {"balance": balance, "free_used": False, "unlimited": True}

        # Use free applications first for any application charge
        if is_app_charge and free_remaining > 0:
            conn.execute(
                "UPDATE users SET free_applications_remaining = free_applications_remaining - 1 WHERE id = %s",
                (user_id,),
            )
            conn.execute(
                """INSERT INTO wallet_transactions
                   (user_id, amount, balance_after, type, reference_id, description)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (user_id, 0.0, balance, "free_application", reference_id,
                 f"Free application used — {description}" if description else "Free application used"),
            )
            conn.commit()
            return {"balance": balance, "free_used": True}

        if balance < amount:
            conn.rollback()
            raise ValueError(f"Insufficient credits: {balance} < {amount}")

        # Atomic debit with RETURNING for accurate balance
        cur = conn.execute(
            "UPDATE users SET wallet_balance = wallet_balance - %s WHERE id = %s RETURNING wallet_balance",
            (amount, user_id),
        )
        new_balance = float(cur.fetchone()[0])

        conn.execute(
            """INSERT INTO wallet_transactions
               (user_id, amount, balance_after, type, reference_id, description)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, -amount, new_balance, tx_type, reference_id, description),
        )
        conn.commit()
        return {"balance": new_balance, "free_used": False}


def check_sufficient_credits(user_id: str, amount: float = 1.0) -> bool:
    """Check if user has enough credits (or free apps) for an application attempt.

    Premium (unlimited subscription) users always pass.
    Reserves against the full credit cost (1.0) since outcome is unknown upfront.
    """
    with _connect() as conn:
        cur = conn.execute(
            "SELECT wallet_balance, free_applications_remaining, is_premium FROM users WHERE id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return False
        if row[2]:  # is_premium
            return True
        balance = float(row[0])
        free_remaining = row[1]
        return free_remaining > 0 or balance >= amount


def set_premium(user_id: str, is_premium: bool = True) -> bool:
    """Set or unset premium status for a user."""
    with _connect() as conn:
        try:
            conn.execute(
                "UPDATE users SET is_premium = %s WHERE id = %s",
                (is_premium, user_id),
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            logger.exception("Failed to set premium for user %s", user_id)
            return False


def delete_user_data(user_id: str) -> bool:
    """Delete all billing data for a user (GDPR deletion).

    Removes all wallet_transactions, then the users row itself.
    Returns True on success, False on error.
    """
    with _connect() as conn:
        try:
            conn.execute(
                "DELETE FROM wallet_transactions WHERE user_id = %s",
                (user_id,),
            )
            conn.execute(
                "DELETE FROM users WHERE id = %s",
                (user_id,),
            )
            conn.commit()
            logger.info("Deleted billing data for user %s", user_id)
            return True
        except Exception:
            conn.rollback()
            logger.exception("Failed to delete billing data for user %s", user_id)
            return False


def get_user_auth_info(email: str) -> Optional[Dict[str, Any]]:
    """Get auth-relevant fields for a user by email. Returns None if not found."""
    with _connect() as conn:
        cur = conn.execute(
            "SELECT id, email, password_hash, auth_provider, name FROM users WHERE email = %s",
            (email,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "email": row[1],
            "password_hash": row[2],
            "auth_provider": row[3] or "google",
            "name": row[4],
        }


def create_user_with_password(email: str, password_hash: str, name: str) -> Dict[str, Any]:
    """Create a new user with email/password auth. Returns user dict."""
    with _connect() as conn:
        user_id = str(uuid.uuid4())

        # Create Stripe customer
        settings = get_settings()
        stripe_customer_id = None
        if settings.STRIPE_SECRET_KEY:
            try:
                stripe.api_key = settings.STRIPE_SECRET_KEY
                customer = stripe.Customer.create(email=email, name=name)
                stripe_customer_id = customer.id
            except Exception as e:
                logger.warning("Failed to create Stripe customer for %s: %s", email, e)

        conn.execute(
            """INSERT INTO users (id, email, password_hash, name, auth_provider, stripe_customer_id)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, email, password_hash, name, "email", stripe_customer_id),
        )
        conn.commit()
        return {
            "id": user_id,
            "email": email,
            "name": name,
            "auth_provider": "email",
        }


def set_user_password(email: str, password_hash: str, name: Optional[str] = None) -> Dict[str, Any]:
    """Set password on an existing user (e.g. Google-only user adding email auth)."""
    with _connect() as conn:
        if name:
            conn.execute(
                "UPDATE users SET password_hash = %s, name = COALESCE(name, %s), auth_provider = 'both' WHERE email = %s",
                (password_hash, name, email),
            )
        else:
            conn.execute(
                "UPDATE users SET password_hash = %s, auth_provider = 'both' WHERE email = %s",
                (password_hash, email),
            )
        conn.commit()

        cur = conn.execute(
            "SELECT id, email, name, auth_provider FROM users WHERE email = %s",
            (email,),
        )
        row = cur.fetchone()
        return {
            "id": str(row[0]),
            "email": row[1],
            "name": row[2],
            "auth_provider": row[3],
        }


def link_google_provider(email: str) -> bool:
    """Mark an email-only user as having linked Google auth."""
    with _connect() as conn:
        try:
            conn.execute(
                "UPDATE users SET auth_provider = 'both' WHERE email = %s AND auth_provider = 'email'",
                (email,),
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            logger.exception("Failed to link Google for %s", email)
            return False


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Get a user by their ID. Returns dict with notification prefs, or None."""
    with _connect() as conn:
        cur = conn.execute(
            "SELECT id, email, notification_channel, phone_number, phone_verified, name FROM users WHERE id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "email": row[1],
            "notification_channel": row[2] or "email",
            "phone_number": row[3],
            "phone_verified": bool(row[4]) if row[4] is not None else False,
            "name": row[5],
        }


def update_notification_channel(user_id: str, channel: str) -> None:
    """Update the notification channel preference for a user."""
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET notification_channel = %s WHERE id = %s",
            (channel, user_id),
        )
        conn.commit()


def get_transactions(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent wallet transactions."""
    with _connect() as conn:
        cur = conn.execute(
            """SELECT id, amount, balance_after, type, reference_id, description, created_at
               FROM wallet_transactions
               WHERE user_id = %s
               ORDER BY created_at DESC
               LIMIT %s""",
            (user_id, limit),
        )
        return [
            {
                "id": str(row[0]),
                "amount": float(row[1]),
                "balance_after": float(row[2]),
                "type": row[3],
                "reference_id": row[4],
                "description": row[5],
                "created_at": row[6].isoformat() if row[6] else None,
            }
            for row in cur.fetchall()
        ]


def create_anonymous_user(email: str, name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Create an anonymous user for a free trial run.

    Returns None if:
    - email already belongs to a real (non-anonymous) account
    - email already used its free trial
    """
    with _connect() as conn:
        cur = conn.execute(
            "SELECT id, is_anonymous, free_applications_remaining, auth_provider FROM users WHERE email = %s",
            (email,),
        )
        row = cur.fetchone()
        if row:
            is_anon = row[1]
            free_remaining = row[2]
            auth_provider = row[3]
            if not is_anon:
                # Real account exists — must sign in
                return None
            if auth_provider == "free_trial" and free_remaining <= 0:
                # Already used free trial
                return None
            # Existing anonymous user with credits remaining — return it
            return {
                "id": str(row[0]),
                "email": email,
                "is_anonymous": True,
            }

        # Create new anonymous user (no Stripe customer — save API calls)
        user_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO users (id, email, name, auth_provider, is_anonymous, free_applications_remaining)
               VALUES (%s, %s, %s, 'free_trial', TRUE, 3)""",
            (user_id, email, name),
        )
        conn.commit()
        return {
            "id": user_id,
            "email": email,
            "is_anonymous": True,
        }


def convert_anonymous_user(
    user_id: str,
    password_hash: Optional[str] = None,
    name: Optional[str] = None,
    auth_provider: str = "email",
) -> Optional[Dict[str, Any]]:
    """Convert an anonymous free-trial user to a full account.

    Creates Stripe customer and flips is_anonymous to FALSE.
    """
    with _connect() as conn:
        cur = conn.execute(
            "SELECT id, email, is_anonymous FROM users WHERE id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        if not row or not row[2]:
            return None  # Not found or not anonymous

        email = row[1]

        # Create Stripe customer
        settings = get_settings()
        stripe_customer_id = None
        if settings.STRIPE_SECRET_KEY:
            try:
                stripe.api_key = settings.STRIPE_SECRET_KEY
                customer = stripe.Customer.create(email=email, name=name)
                stripe_customer_id = customer.id
            except Exception as e:
                logger.warning("Failed to create Stripe customer for %s: %s", email, e)

        updates = ["is_anonymous = FALSE", "auth_provider = %s", "stripe_customer_id = %s"]
        params: list = [auth_provider, stripe_customer_id]
        if password_hash:
            updates.append("password_hash = %s")
            params.append(password_hash)
        if name:
            updates.append("name = COALESCE(name, %s)")
            params.append(name)
        params.append(user_id)

        conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = %s",
            params,
        )
        conn.commit()
        return {
            "id": user_id,
            "email": email,
            "name": name,
            "auth_provider": auth_provider,
        }


async def cleanup_anonymous_users(max_age_days: int = 30) -> int:
    """Delete anonymous users (and their transactions) older than max_age_days.

    Returns the number of users deleted.
    """
    with _connect() as conn:
        try:
            # Find stale anonymous users
            cur = conn.execute(
                """SELECT id FROM users
                   WHERE is_anonymous = TRUE
                     AND created_at < NOW() - INTERVAL '%s days'""",
                (max_age_days,),
            )
            stale_ids = [str(row[0]) for row in cur.fetchall()]
            if not stale_ids:
                return 0

            # Delete their transactions first (FK constraint)
            conn.execute(
                "DELETE FROM wallet_transactions WHERE user_id = ANY(%s::uuid[])",
                (stale_ids,),
            )
            # Delete their sessions
            conn.execute(
                "DELETE FROM sessions WHERE user_id = ANY(%s)",
                (stale_ids,),
            )
            # Delete the users
            cur = conn.execute(
                "DELETE FROM users WHERE id = ANY(%s::uuid[]) RETURNING id",
                (stale_ids,),
            )
            deleted = cur.rowcount
            conn.commit()
            logger.info("Cleaned up %d anonymous users older than %d days", deleted, max_age_days)
            return deleted
        except Exception:
            conn.rollback()
            logger.exception("Failed to clean up anonymous users")
            return 0
