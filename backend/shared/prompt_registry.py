# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Postgres-backed prompt registry for self-improving agent prompts.

Stores versioned prompts that EvoAgentX TextGrad can optimize over time.
Agents load the active prompt for each key at runtime, falling back to
their hardcoded default if no active prompt exists in the registry.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from backend.shared.db import get_pool

logger = logging.getLogger(__name__)

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS prompt_registry (
    id SERIAL PRIMARY KEY,
    prompt_key TEXT NOT NULL,
    version INT NOT NULL DEFAULT 1,
    prompt_text TEXT NOT NULL,
    score FLOAT,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB
);
"""

_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_prompt_key_version
    ON prompt_registry (prompt_key, version);
"""

_ensured = False


def _ensure_table() -> None:
    global _ensured
    if _ensured:
        return
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(_TABLE_SQL)
        conn.execute(_INDEX_SQL)
        conn.commit()
    _ensured = True


def get_active_prompt(key: str) -> Optional[str]:
    """Return the active prompt text for a key, or None if not found."""
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT prompt_text FROM prompt_registry WHERE prompt_key = %s AND is_active = TRUE",
            (key,),
        ).fetchone()
    if row:
        return row[0]
    return None


def save_prompt(
    key: str,
    text: str,
    score: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> int:
    """Save a new prompt version. Returns the new version number."""
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        # Get next version number
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM prompt_registry WHERE prompt_key = %s",
            (key,),
        ).fetchone()
        next_version = row[0]

        conn.execute(
            """
            INSERT INTO prompt_registry (prompt_key, version, prompt_text, score, metadata)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (key, next_version, text, score, json.dumps(metadata) if metadata else None),
        )
        conn.commit()

    logger.info("Saved prompt '%s' v%d (score=%s)", key, next_version, score)
    return next_version


def activate_prompt(key: str, version: int) -> None:
    """Set one version as active, deactivating all others for this key."""
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE prompt_registry SET is_active = FALSE WHERE prompt_key = %s",
            (key,),
        )
        conn.execute(
            "UPDATE prompt_registry SET is_active = TRUE WHERE prompt_key = %s AND version = %s",
            (key, version),
        )
        conn.commit()
    logger.info("Activated prompt '%s' v%d", key, version)


def get_prompt_history(key: str, limit: int = 10) -> list:
    """Return recent versions for a prompt key."""
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT version, score, is_active, created_at
               FROM prompt_registry
               WHERE prompt_key = %s
               ORDER BY version DESC
               LIMIT %s""",
            (key, limit),
        ).fetchall()
    return [
        {"version": r[0], "score": r[1], "is_active": r[2], "created_at": r[3].isoformat() if r[3] else None}
        for r in rows
    ]
