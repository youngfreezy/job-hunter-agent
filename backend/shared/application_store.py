"""Persistent storage for application results.

Writes each application attempt (submitted/failed/skipped) to Postgres
immediately, so results survive backend restarts and are always available
for the Manual Apply / Application Log UI.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS application_results (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    status TEXT NOT NULL,
    job_title TEXT,
    job_company TEXT,
    job_url TEXT,
    job_board TEXT,
    job_location TEXT,
    error_message TEXT,
    cover_letter TEXT,
    tailored_resume_text TEXT,
    duration_seconds INT,
    screenshot_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_app_results_session ON application_results(session_id);
CREATE INDEX IF NOT EXISTS idx_app_results_session_status ON application_results(session_id, status);
CREATE INDEX IF NOT EXISTS idx_app_results_job_id_status ON application_results(job_id, status);
"""


def _connect() -> psycopg.Connection:
    settings = get_settings()
    return psycopg.connect(settings.DATABASE_URL)


async def ensure_table() -> None:
    """Create the application_results table if it doesn't exist."""
    try:
        conn = _connect()
        try:
            conn.execute(_CREATE_TABLE)
            # Migration: add screenshot_path column if missing
            conn.execute("""
                ALTER TABLE application_results
                ADD COLUMN IF NOT EXISTS screenshot_path TEXT
            """)
            conn.commit()
            logger.info("application_results table ensured")
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to ensure application_results table")


def record_result(
    session_id: str,
    job_id: str,
    status: str,
    job_title: str = "",
    job_company: str = "",
    job_url: str = "",
    job_board: str = "",
    job_location: str = "",
    error_message: Optional[str] = None,
    cover_letter: Optional[str] = None,
    tailored_resume_text: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    screenshot_path: Optional[str] = None,
) -> None:
    """Insert a single application result row."""
    try:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO application_results
                    (session_id, job_id, status, job_title, job_company, job_url,
                     job_board, job_location, error_message, cover_letter,
                     tailored_resume_text, duration_seconds, screenshot_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (session_id, job_id, status, job_title, job_company, job_url,
                 job_board, job_location, error_message, cover_letter,
                 tailored_resume_text, duration_seconds, screenshot_path),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to record application result for %s", job_id)


def check_already_applied(job_id: str) -> Optional[Dict[str, Any]]:
    """Check if this job was already submitted (any session).

    Returns the prior application record if found, None otherwise.
    Only ``submitted`` status counts -- failed/skipped don't block re-attempts.
    """
    try:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                SELECT session_id, job_title, job_company, created_at
                FROM application_results
                WHERE job_id = %s AND status = 'submitted'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (job_id,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "session_id": row[0],
                    "job_title": row[1],
                    "job_company": row[2],
                    "applied_at": row[3].isoformat() if row[3] else None,
                }
            return None
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to check duplicate for %s", job_id)
        return None


def get_results_for_session(session_id: str) -> List[Dict[str, Any]]:
    """Return all application results for a session, ordered by creation time."""
    try:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                SELECT job_id, status, job_title, job_company, job_url,
                       job_board, job_location, error_message, cover_letter,
                       tailored_resume_text, duration_seconds, created_at,
                       screenshot_path
                FROM application_results
                WHERE session_id = %s
                ORDER BY created_at ASC
                """,
                (session_id,),
            )
            rows = cur.fetchall()
            return [
                {
                    "status": r[1],
                    "job": {
                        "id": r[0],
                        "title": r[2] or "",
                        "company": r[3] or "",
                        "url": r[4] or "",
                        "board": r[5] or "",
                        "location": r[6] or "",
                    },
                    "error": r[7],
                    "cover_letter": r[8] or "",
                    "tailored_resume": {"tailored_text": r[9], "fit_score": 0, "changes_made": []} if r[9] else None,
                    "duration": r[10],
                    "submitted_at": r[11].isoformat() if r[11] else None,
                    "screenshot_path": r[12] or None,
                }
                for r in rows
            ]
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to get application results for session %s", session_id)
        return []
