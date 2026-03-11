# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Persist Skyvern screenshots and task artifacts in Postgres.

Skyvern's Railway container is ephemeral — screenshots and task data vanish
on every deploy. This module persists them so we can debug against real
artifacts instead of guessing from log text.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

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

_ARTIFACT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS skyvern_task_artifacts (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    skyvern_status TEXT NOT NULL,
    failure_reason TEXT,
    extracted_information JSONB,
    screenshot_url TEXT,
    action_screenshot_urls JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_failure_screenshots_session
    ON failure_screenshots (session_id);
"""

_ARTIFACT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_skyvern_artifacts_session
    ON skyvern_task_artifacts (session_id);
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
        conn.execute(_ARTIFACT_TABLE_SQL)
        conn.execute(_ARTIFACT_INDEX_SQL)
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
    """Delete all screenshots and artifacts for a session (GDPR). Returns count deleted."""
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        r1 = conn.execute(
            "DELETE FROM failure_screenshots WHERE session_id = %s", (session_id,)
        )
        r2 = conn.execute(
            "DELETE FROM skyvern_task_artifacts WHERE session_id = %s", (session_id,)
        )
        conn.commit()
    return r1.rowcount + r2.rowcount


# ---------------------------------------------------------------------------
# Skyvern task artifact persistence
# ---------------------------------------------------------------------------


async def store_task_artifact(
    *,
    session_id: str,
    job_id: str,
    task_id: str,
    skyvern_status: str,
    failure_reason: str = "",
    extracted_information: Optional[Dict[str, Any]] = None,
    screenshot_url: Optional[str] = None,
    action_screenshot_urls: Optional[List[str]] = None,
) -> Optional[int]:
    """Persist the full Skyvern task result for post-hoc debugging.

    Stored for every task outcome (success, failure, skip) so we always
    have artifacts to inspect.
    """
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO skyvern_task_artifacts
                (session_id, job_id, task_id, skyvern_status, failure_reason,
                 extracted_information, screenshot_url, action_screenshot_urls)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                session_id,
                job_id,
                task_id,
                skyvern_status,
                failure_reason or None,
                json.dumps(extracted_information) if extracted_information else None,
                screenshot_url,
                json.dumps(action_screenshot_urls) if action_screenshot_urls else None,
            ),
        ).fetchone()
        conn.commit()

    row_id = row[0] if row else None
    logger.info(
        "Stored Skyvern artifact for session=%s job=%s task=%s status=%s (id=%s)",
        session_id, job_id, task_id, skyvern_status, row_id,
    )
    return row_id


def get_artifacts_for_session(session_id: str) -> list[dict]:
    """Return all Skyvern task artifacts for a session."""
    _ensure_table()
    pool = get_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT id, job_id, task_id, skyvern_status, failure_reason,
                      extracted_information, screenshot_url, action_screenshot_urls,
                      created_at
               FROM skyvern_task_artifacts
               WHERE session_id = %s
               ORDER BY created_at""",
            (session_id,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "job_id": r[1],
            "task_id": r[2],
            "skyvern_status": r[3],
            "failure_reason": r[4],
            "extracted_information": r[5],
            "screenshot_url": r[6],
            "action_screenshot_urls": r[7],
            "created_at": r[8].isoformat() if r[8] else None,
        }
        for r in rows
    ]
