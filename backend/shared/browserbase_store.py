# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Per-user Browserbase settings.

Each user can store their own Browserbase API key (encrypted at rest with the
same Fernet key as board credentials), project id, proxy preference and the
persisted-login Context id for each job board.  These override the
``BROWSERBASE_*`` environment settings for that user's sessions.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from backend.shared.credential_store import _decrypt, _encrypt
from backend.shared.db import get_connection

logger = logging.getLogger(__name__)

# Boards a Context id can be stored for. "default" is used for any other board.
CONTEXT_BOARDS = ("indeed", "glassdoor", "ziprecruiter", "default")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS browserbase_settings (
    user_id UUID PRIMARY KEY,
    encrypted_api_key TEXT,
    project_id TEXT,
    proxies BOOLEAN NOT NULL DEFAULT FALSE,
    context_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""

_ensured = False


def _ensure_table(conn: Any) -> None:
    """Create the table on first use (alembic o2b3c4d5e6f7 does the same)."""
    global _ensured
    if _ensured:
        return
    conn.execute(_CREATE_TABLE)
    conn.commit()
    _ensured = True


def _clean_context_ids(context_ids: Optional[Dict[str, Any]]) -> Dict[str, str]:
    cleaned: Dict[str, str] = {}
    for board, ctx in (context_ids or {}).items():
        key = str(board).strip().lower()
        value = str(ctx or "").strip()
        if key in CONTEXT_BOARDS and value:
            cleaned[key] = value
    return cleaned


def _row_to_dict(row: Any) -> Dict[str, Any]:
    encrypted_api_key, project_id, proxies, context_ids = row
    api_key = None
    if encrypted_api_key:
        api_key = (_decrypt(encrypted_api_key) or {}).get("api_key") or None
    if isinstance(context_ids, str):
        context_ids = json.loads(context_ids)
    return {
        "api_key": api_key,
        "project_id": project_id or None,
        "proxies": bool(proxies),
        "context_ids": _clean_context_ids(context_ids),
    }


def get_browserbase_settings(user_id: str) -> Optional[Dict[str, Any]]:
    """Return the user's settings with the API key decrypted, or None."""
    with get_connection() as conn:
        _ensure_table(conn)
        row = conn.execute(
            "SELECT encrypted_api_key, project_id, proxies, context_ids "
            "FROM browserbase_settings WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def save_browserbase_settings(
    user_id: str,
    *,
    api_key: Optional[str],
    project_id: Optional[str],
    proxies: bool,
    context_ids: Optional[Dict[str, Any]],
    keep_api_key: bool = False,
) -> Dict[str, Any]:
    """Insert or update the user's settings.

    With *keep_api_key* the stored key is left untouched (the UI never echoes
    the key back, so "save" without retyping it must not blank it).
    """
    encrypted = _encrypt({"api_key": api_key.strip()}) if api_key and api_key.strip() else None
    cleaned_ids = json.dumps(_clean_context_ids(context_ids))
    project = (project_id or "").strip() or None
    with get_connection() as conn:
        _ensure_table(conn)
        if keep_api_key:
            conn.execute(
                """
                INSERT INTO browserbase_settings (user_id, encrypted_api_key, project_id, proxies, context_ids, updated_at)
                VALUES (%s, NULL, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    project_id = EXCLUDED.project_id,
                    proxies = EXCLUDED.proxies,
                    context_ids = EXCLUDED.context_ids,
                    updated_at = NOW()
                """,
                (user_id, project, proxies, cleaned_ids),
            )
        else:
            conn.execute(
                """
                INSERT INTO browserbase_settings (user_id, encrypted_api_key, project_id, proxies, context_ids, updated_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    encrypted_api_key = EXCLUDED.encrypted_api_key,
                    project_id = EXCLUDED.project_id,
                    proxies = EXCLUDED.proxies,
                    context_ids = EXCLUDED.context_ids,
                    updated_at = NOW()
                """,
                (user_id, encrypted, project, proxies, cleaned_ids),
            )
        conn.commit()
    return get_browserbase_settings(user_id) or {}


def set_context_id(user_id: str, board: str, context_id: str) -> None:
    """Store the persisted-login Context id for one board (after login capture)."""
    key = board.strip().lower()
    if key not in CONTEXT_BOARDS:
        raise ValueError(f"Unsupported board for a Browserbase Context: {board}")
    if not context_id.strip():
        raise ValueError("context_id is empty")
    with get_connection() as conn:
        _ensure_table(conn)
        conn.execute(
            """
            INSERT INTO browserbase_settings (user_id, context_ids, updated_at)
            VALUES (%s, %s::jsonb, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                context_ids = browserbase_settings.context_ids || EXCLUDED.context_ids,
                updated_at = NOW()
            """,
            (user_id, json.dumps({key: context_id.strip()})),
        )
        conn.commit()
    logger.info("Stored Browserbase Context for user %s board %s", user_id, key)


def delete_browserbase_settings(user_id: str) -> bool:
    with get_connection() as conn:
        _ensure_table(conn)
        cur = conn.execute("DELETE FROM browserbase_settings WHERE user_id = %s", (user_id,))
        conn.commit()
        return cur.rowcount > 0
