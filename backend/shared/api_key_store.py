# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""API key generation, hashing, and validation for the developer platform."""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from typing import Any, Dict, List, Optional

from backend.shared.db import get_connection

logger = logging.getLogger(__name__)

_KEY_PREFIX = "jh_live_"


def generate_api_key(user_id: str, name: str) -> Dict[str, Any]:
    """Generate a new API key. Returns the key (shown ONCE) and metadata.

    The raw key is never stored — only its SHA-256 hash.
    """
    raw_key = f"{_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_id = str(uuid.uuid4())

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO api_keys (id, user_id, key_hash, key_prefix, name)
               VALUES (%s, %s, %s, %s, %s)""",
            (key_id, user_id, key_hash, raw_key[:16], name),
        )
        conn.commit()

    return {
        "id": key_id,
        "key": raw_key,  # Only returned once!
        "key_prefix": raw_key[:16],
        "name": name,
    }


def list_api_keys(user_id: str) -> List[Dict[str, Any]]:
    """List all API keys for a user (prefix only, never the full key)."""
    with get_connection() as conn:
        cur = conn.execute(
            """SELECT id, key_prefix, name, is_active, last_used_at, created_at
               FROM api_keys
               WHERE user_id = %s
               ORDER BY created_at DESC""",
            (user_id,),
        )
        return [
            {
                "id": str(row[0]),
                "key_prefix": row[1],
                "name": row[2],
                "is_active": row[3],
                "last_used_at": row[4].isoformat() if row[4] else None,
                "created_at": row[5].isoformat() if row[5] else None,
            }
            for row in cur.fetchall()
        ]


def revoke_api_key(key_id: str, user_id: str) -> bool:
    """Revoke (deactivate) an API key. Returns True if found and revoked."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE api_keys SET is_active = FALSE WHERE id = %s AND user_id = %s RETURNING id",
            (key_id, user_id),
        )
        revoked = cur.fetchone() is not None
        conn.commit()
        return revoked


def validate_api_key(raw_key: str) -> Optional[Dict[str, Any]]:
    """Validate an API key and return the owning user's info, or None if invalid.

    Also updates last_used_at timestamp.
    """
    if not raw_key.startswith(_KEY_PREFIX):
        return None

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    with get_connection() as conn:
        cur = conn.execute(
            """SELECT ak.id, ak.user_id, u.email
               FROM api_keys ak
               JOIN users u ON u.id = ak.user_id
               WHERE ak.key_hash = %s AND ak.is_active = TRUE""",
            (key_hash,),
        )
        row = cur.fetchone()
        if not row:
            return None

        # Update last_used_at
        conn.execute(
            "UPDATE api_keys SET last_used_at = NOW() WHERE id = %s",
            (row[0],),
        )
        conn.commit()
        return {"id": str(row[0]), "user_id": str(row[1]), "email": row[2]}
