# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Persist encrypted resume files in Postgres so they survive deploys.

Resumes were previously stored in /tmp which is ephemeral on Railway.
This module stores the encrypted bytes in a BYTEA column keyed by
session_id, and reconstructs temp files on demand for Skyvern to download.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

from backend.shared.db import get_pool

logger = logging.getLogger(__name__)

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS resume_files (
    session_id TEXT PRIMARY KEY,
    encrypted_data BYTEA NOT NULL,
    original_extension TEXT NOT NULL DEFAULT '.pdf',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

_ensured = False


def _ensure_table() -> None:
    global _ensured
    if _ensured:
        return
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(_TABLE_SQL)
        conn.commit()
    _ensured = True


def save_resume(session_id: str, encrypted_data: bytes, extension: str = ".pdf") -> None:
    """Store encrypted resume bytes in Postgres."""
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO resume_files (session_id, encrypted_data, original_extension)
            VALUES (%s, %s, %s)
            ON CONFLICT (session_id)
            DO UPDATE SET encrypted_data = EXCLUDED.encrypted_data,
                          original_extension = EXCLUDED.original_extension
            """,
            (session_id, encrypted_data, extension),
        )
        conn.commit()
    logger.info("Resume saved to DB for session %s (%d bytes)", session_id, len(encrypted_data))


def get_resume(session_id: str) -> Optional[tuple[bytes, str]]:
    """Retrieve encrypted resume bytes and extension from Postgres.

    Returns (encrypted_data, extension) or None if not found.
    """
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT encrypted_data, original_extension FROM resume_files WHERE session_id = %s",
            (session_id,),
        ).fetchone()
    if row:
        return (bytes(row[0]), row[1])
    return None


def get_resume_bytes(session_id: str) -> Optional[tuple[bytes, str]]:
    """Canonical way to get decrypted resume bytes for a session.

    Returns (plaintext_pdf_bytes, extension) or None.
    Always reads from Postgres — never touches /tmp.
    """
    row = get_resume(session_id)
    if not row:
        return None
    encrypted_data, ext = row
    from backend.shared.resume_crypto import _get_fernet
    return (_get_fernet().decrypt(encrypted_data), ext)


def get_latest_resume_for_user(user_id: str) -> Optional[tuple[bytes, str]]:
    """Get the most recent decrypted resume for a user (across all sessions).

    Joins resume_files with sessions to find the latest resume uploaded
    by this user. Returns (plaintext_bytes, extension) or None.
    """
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT rf.encrypted_data, rf.original_extension
            FROM resume_files rf
            JOIN sessions s ON s.id::text = rf.session_id
            WHERE s.user_id = %s
            ORDER BY rf.created_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    if not row:
        return None
    encrypted_data, ext = bytes(row[0]), row[1]
    from backend.shared.resume_crypto import _get_fernet
    return (_get_fernet().decrypt(encrypted_data), ext)


def delete_resume(session_id: str) -> None:
    """Delete a resume from Postgres."""
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute("DELETE FROM resume_files WHERE session_id = %s", (session_id,))
        conn.commit()
