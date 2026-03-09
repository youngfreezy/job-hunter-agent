# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Authentication routes.

NextAuth handles authentication on the frontend (Next.js).
This module provides /api/auth/me to resolve the backend user
from the JWT token set by JWTAuthMiddleware, plus email/password
registration and login endpoints.
"""

import hmac
import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from passlib.hash import bcrypt
from pydantic import BaseModel, EmailStr, field_validator

from backend.gateway.deps import get_current_user
from backend.shared.billing_store import (
    create_user_with_password,
    get_user_auth_info,
    link_google_provider,
    set_user_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Pre-computed bcrypt hash for timing normalization (prevents user-existence oracle)
# Generated from: bcrypt.hash("dummy")
_DUMMY_HASH: str | None = None


def _get_dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = bcrypt.hash("dummy")
    return _DUMMY_HASH

# Internal secret for server-to-server link-google calls from NextAuth
_LINK_GOOGLE_SECRET = os.environ.get("NEXTAUTH_SECRET", "")

_MAX_PASSWORD_LENGTH = 128


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > _MAX_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at most {_MAX_PASSWORD_LENGTH} characters")
        return v

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_max_length(cls, v: str) -> str:
        if len(v) > _MAX_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at most {_MAX_PASSWORD_LENGTH} characters")
        return v


class LinkGoogleRequest(BaseModel):
    email: EmailStr
    secret: str  # Must match NEXTAUTH_SECRET to prevent unauthorized calls


# ---------------------------------------------------------------------------
# Public endpoints (no JWT required)
# ---------------------------------------------------------------------------

@router.post("/register")
async def register(body: RegisterRequest):
    """Register a new user with email and password."""
    existing = get_user_auth_info(body.email)

    if existing and existing["password_hash"]:
        # Already has a password — return generic success to prevent email enumeration
        # The user will fail at the signIn step with "Invalid credentials"
        return JSONResponse(
            status_code=200,
            content={"email": body.email, "name": body.name},
        )

    if existing and not existing["password_hash"]:
        # Google-only user — don't allow unauthenticated password-setting.
        # Return generic success to prevent enumeration. User should sign in
        # with Google first, then set a password from settings.
        return JSONResponse(
            status_code=200,
            content={"email": body.email, "name": body.name},
        )

    # Brand new user
    hashed = bcrypt.hash(body.password)
    user = create_user_with_password(body.email, hashed, body.name)
    logger.info("New email/password user registered: %s", body.email)
    return JSONResponse(
        status_code=200,
        content={"email": user["email"], "name": user["name"]},
    )


@router.post("/login")
async def login(body: LoginRequest):
    """Authenticate with email and password."""
    user = get_user_auth_info(body.email)

    if not user:
        # Normalize timing: run bcrypt even when user not found
        bcrypt.verify(body.password, _get_dummy_hash())
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid email or password"},
        )

    if not user["password_hash"]:
        # Google-only account — normalize timing then return generic error
        bcrypt.verify(body.password, _get_dummy_hash())
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid email or password"},
        )

    if not bcrypt.verify(body.password, user["password_hash"]):
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid email or password"},
        )

    logger.info("Email/password login for %s", body.email)
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
    }


@router.post("/link-google")
async def link_google(body: LinkGoogleRequest):
    """Mark an email-only user as having linked Google auth.

    Protected by a shared secret (NEXTAUTH_SECRET) — only callable from
    the NextAuth signIn callback on the server side.
    """
    if not _LINK_GOOGLE_SECRET or not hmac.compare_digest(body.secret, _LINK_GOOGLE_SECRET):
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    link_google_provider(body.email)
    return {"linked": True}


# ---------------------------------------------------------------------------
# Authenticated endpoints
# ---------------------------------------------------------------------------

@router.get("/me")
async def me(request: Request):
    """Return the current user resolved from JWT authentication."""
    user = get_current_user(request)
    return {"user": user}


class NotificationChannelUpdate(BaseModel):
    notification_channel: str


@router.put("/me/notification-channel")
async def update_notification_channel(request: Request, body: NotificationChannelUpdate):
    """Update the user's notification channel preference (email, sms, or both)."""
    user = get_current_user(request)
    if body.notification_channel not in ("email", "sms", "both"):
        return JSONResponse(status_code=400, content={"detail": "Invalid channel. Must be email, sms, or both."})
    from backend.shared.billing_store import update_notification_channel as _update_channel
    _update_channel(user["id"], body.notification_channel)
    return {"notification_channel": body.notification_channel}


@router.delete("/me/data")
async def delete_user_data(request: Request):
    """GDPR: permanently delete all data associated with the current user."""
    from backend.gateway.routes.sessions import session_registry
    from backend.shared.application_store import delete_application_results_for_sessions
    from backend.shared.billing_store import delete_user_data as delete_billing_data
    from backend.shared.redis_client import redis_client

    user = get_current_user(request)
    user_id = user["id"]
    user_email = user["email"]
    logger.info("GDPR delete requested for user %s (%s)", user_id, user_email)

    # 1. Collect session IDs owned by this user
    user_session_ids = [
        sid
        for sid, meta in session_registry.items()
        if meta.get("user_id") == user_id
    ]

    # 2. Delete application results for those sessions
    app_deleted = delete_application_results_for_sessions(user_session_ids)

    # 3. Delete billing data (wallet_transactions + users row)
    billing_deleted = delete_billing_data(user_id)

    # 4. Clear Redis keys for this user's sessions (gmail tokens)
    redis_keys_deleted = 0
    for sid in user_session_ids:
        try:
            await redis_client.delete(f"gmail_token:{sid}")
            redis_keys_deleted += 1
        except Exception:
            logger.exception("Failed to delete gmail_token for session %s", sid)

    # 5. Clear rate-limit keys for this user
    try:
        rl_pattern = f"ratelimit:user:{user_id}:*"
        keys = await redis_client.client.keys(rl_pattern)
        if keys:
            await redis_client.client.delete(*keys)
            redis_keys_deleted += len(keys)
    except Exception:
        logger.exception("Failed to clear rate-limit keys for user %s", user_id)

    # 6. Remove sessions from in-memory registry
    for sid in user_session_ids:
        session_registry.pop(sid, None)

    success = app_deleted and billing_deleted
    status_code = 200 if success else 207

    return JSONResponse(
        status_code=status_code,
        content={
            "deleted": True,
            "user_id": user_id,
            "sessions_cleared": len(user_session_ids),
            "redis_keys_deleted": redis_keys_deleted,
            "billing_deleted": billing_deleted,
            "application_results_deleted": app_deleted,
        },
    )
