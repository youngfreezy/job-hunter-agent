# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Persist Skyvern failure screenshots in Postgres for the feedback loop.

Screenshots are ephemeral on Skyvern's Railway container — they vanish on
every deploy.  This module downloads and stores them as BYTEA so the
self-improvement loop can analyze failure patterns over time.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from backend.shared.db import get_pool

logger = logging.getLogger(__name__)

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS failure_screenshots (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    image_data BYTEA NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'image/png',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_failure_screenshots_session
    ON failure_screenshots (session_id);
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


async def download_and_store(
    session_id: str,
    job_id: str,
    screenshot_url: str,
) -> Optional[int]:
    """Download a screenshot from Skyvern and persist to Postgres.

    Returns the row ID on success, None on failure.
    """
    if not screenshot_url:
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(screenshot_url)
            resp.raise_for_status()
            image_data = resp.content
            content_type = resp.headers.get("content-type", "image/png")
    except Exception as exc:
        logger.warning(
            "Failed to download screenshot %s for job %s: %s",
            screenshot_url, job_id, exc,
        )
        return None

    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO failure_screenshots (session_id, job_id, image_data, content_type)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (session_id, job_id, image_data, content_type),
        ).fetchone()
        conn.commit()

    row_id = row[0] if row else None
    logger.info(
        "Stored failure screenshot for session=%s job=%s (%d bytes, id=%s)",
        session_id, job_id, len(image_data), row_id,
    )
    return row_id


def get_screenshot(screenshot_id: int) -> Optional[tuple[bytes, str]]:
    """Retrieve screenshot bytes and content_type by ID.

    Returns (image_data, content_type) or None.
    """
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT image_data, content_type FROM failure_screenshots WHERE id = %s",
            (screenshot_id,),
        ).fetchone()
    if row:
        return (bytes(row[0]), row[1])
    return None


def get_screenshots_for_session(session_id: str) -> list[dict]:
    """Return metadata for all screenshots in a session."""
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT id, job_id, content_type, length(image_data), created_at
               FROM failure_screenshots
               WHERE session_id = %s
               ORDER BY created_at""",
            (session_id,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "job_id": r[1],
            "content_type": r[2],
            "size_bytes": r[3],
            "created_at": r[4].isoformat() if r[4] else None,
        }
        for r in rows
    ]


def delete_for_session(session_id: str) -> int:
    """Delete all screenshots for a session (GDPR). Returns count deleted."""
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        result = conn.execute(
            "DELETE FROM failure_screenshots WHERE session_id = %s", (session_id,)
        )
        conn.commit()
    return result.rowcount
