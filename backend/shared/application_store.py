# Copyright (c) 2026 V2 Software LLC. All rights reserved.

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

from backend.shared.db import get_connection

logger = logging.getLogger(__name__)


class DuplicateCheckUnavailable(RuntimeError):
    """Prior delivery could not be checked; no submission is permitted."""


class SubmissionAlreadyClaimed(RuntimeError):
    """A confirmed or uncertain application already owns this submission."""


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS application_results (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id UUID,
    job_id TEXT NOT NULL,
    status TEXT NOT NULL,
    job_title TEXT,
    job_company TEXT,
    job_url TEXT,
    job_board TEXT,
    job_location TEXT,
    error_message TEXT,
    error_category TEXT,
    ats_type TEXT,
    failure_step TEXT,
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


def _connect():
    return get_connection()


async def ensure_table() -> None:
    """Create the application_results table if it doesn't exist."""
    try:
        with _connect() as conn:
            conn.execute(_CREATE_TABLE)
            # Migrations: add columns if missing
            conn.execute("""
                ALTER TABLE application_results
                ADD COLUMN IF NOT EXISTS screenshot_path TEXT
            """)
            conn.execute("""
                ALTER TABLE application_results
                ADD COLUMN IF NOT EXISTS user_id UUID
            """)
            conn.execute("""
                ALTER TABLE application_results
                ADD COLUMN IF NOT EXISTS error_category TEXT
            """)
            conn.execute("""
                ALTER TABLE application_results
                ADD COLUMN IF NOT EXISTS ats_type TEXT
            """)
            conn.execute("""
                ALTER TABLE application_results
                ADD COLUMN IF NOT EXISTS failure_step TEXT
            """)
            # Index for cross-session URL-based dedup
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_app_results_user_url_status
                ON application_results(user_id, job_url, status)
            """)
            conn.commit()
            logger.info("application_results table ensured")
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
    error_category: Optional[str] = None,
    ats_type: Optional[str] = None,
    failure_step: Optional[str] = None,
    cover_letter: Optional[str] = None,
    tailored_resume_text: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    screenshot_path: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    """Insert a single application result row."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO application_results
                    (session_id, user_id, job_id, status, job_title, job_company, job_url,
                     job_board, job_location, error_message, error_category, ats_type,
                     failure_step, cover_letter, tailored_resume_text, duration_seconds,
                     screenshot_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (session_id, user_id, job_id, status, job_title, job_company, job_url,
                 job_board, job_location, error_message, error_category, ats_type,
                 failure_step, cover_letter, tailored_resume_text, duration_seconds,
                 screenshot_path),
            )
            # Replace intent in the same transaction as its blocking final result.
            # A failed write leaves the intent intact and prevents an unsafe retry.
            if status == "submitted" or error_category == "submission_uncertain":
                conn.execute(
                    """DELETE FROM application_results
                       WHERE session_id = %s AND job_id = %s AND status = 'pending'
                         AND error_category = 'submission_uncertain'""",
                    (session_id, job_id),
                )
            conn.commit()
    except Exception:
        logger.exception("Failed to record application result for %s", job_id)


def check_already_applied(
    job_id: str, user_id: Optional[str] = None, job_url: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Check for a submitted or uncertain submission by this user.

    Returns the prior application record if found, None otherwise.
    Raises DuplicateCheckUnavailable if storage cannot establish that result.
    A possible submission remains on hold until its result is reconciled.
    Ordinary failed, skipped, and pending results do not block re-attempts.
    Checks both by job_id and by job_url (for backward compat with old random IDs).
    """
    try:
        with _connect() as conn:
            # Check by job_id first
            if user_id:
                cur = conn.execute(
                    """
                    SELECT session_id, job_title, job_company, created_at, status, error_category
                    FROM application_results
                    WHERE job_id = %s AND user_id = %s AND (status = 'submitted' OR error_category = 'submission_uncertain')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (job_id, user_id),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT session_id, job_title, job_company, created_at, status, error_category
                    FROM application_results
                    WHERE job_id = %s AND (status = 'submitted' OR error_category = 'submission_uncertain')
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
                    "status": row[4],
                    "error_category": row[5],
                }

            # Fallback: check by URL (handles old records with random UUIDs)
            if job_url and user_id:
                cur = conn.execute(
                    """
                    SELECT session_id, job_title, job_company, created_at, status, error_category
                    FROM application_results
                    WHERE job_url = %s AND user_id = %s AND (status = 'submitted' OR error_category = 'submission_uncertain')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (job_url, user_id),
                )
                row = cur.fetchone()
                if row:
                    return {
                        "session_id": row[0],
                        "job_title": row[1],
                        "job_company": row[2],
                        "applied_at": row[3].isoformat() if row[3] else None,
                        "status": row[4],
                        "error_category": row[5],
                    }

            return None
    except Exception as exc:
        logger.warning("Failed to check duplicate for %s", job_id, exc_info=True)
        raise DuplicateCheckUnavailable(
            "Could not verify prior applications. Application paused before submission; try again when storage is available."
        ) from exc


def mark_submission_intent(session_id: str, job_id: str) -> None:
    """Durably mark the existing attempt immediately before its final submit.

    Keep the attempt's owner and original source URL for cross-session dedup.
    Unlike ordinary result logging, any persistence failure must stop the click.
    """
    with _connect() as conn:
        pending = conn.execute(
            """SELECT user_id, job_url FROM application_results
               WHERE session_id = %s AND job_id = %s AND status = 'pending'
               ORDER BY id DESC LIMIT 1""",
            (session_id, job_id),
        ).fetchone()
        if not pending:
            raise RuntimeError("Cannot submit without a persisted pending application")
        user_id, job_url = pending
        if not user_id:
            raise RuntimeError("Cannot submit without a persisted application owner")
        # Serialize only the brief claim transaction for this owner. Locking by
        # owner covers legacy job IDs that identify the same job through its URL.
        # Provider/browser work runs only after this transaction commits.
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                     (f'application-submit:{user_id}',))
        prior = conn.execute(
            """SELECT 1 FROM application_results
               WHERE user_id = %s AND (job_id = %s OR (job_url = %s AND job_url <> ''))
                 AND (status = 'submitted' OR error_category = 'submission_uncertain')
               LIMIT 1""",
            (user_id, job_id, job_url),
        ).fetchone()
        if prior:
            raise SubmissionAlreadyClaimed(
                "A previous submission exists or remains unverified. Reconcile it before applying again."
            )
        updated = conn.execute(
            """UPDATE application_results
               SET error_category = 'submission_uncertain',
                   error_message = 'Final submission started; receipt not yet verified.'
               WHERE session_id = %s AND job_id = %s AND user_id = %s AND status = 'pending'""",
            (session_id, job_id, user_id),
        )
        if updated.rowcount == 0:
            raise RuntimeError("Cannot submit without a persisted pending application")
        conn.commit()


def clear_pending(session_id: str, job_id: str) -> None:
    """Clear preparation records while retaining any unresolved submission intent."""
    try:
        with _connect() as conn:
            conn.execute(
                """DELETE FROM application_results WHERE session_id = %s AND job_id = %s
                   AND status = 'pending' AND error_category IS DISTINCT FROM 'submission_uncertain'""",
                (session_id, job_id),
            )
            conn.commit()
    except Exception:
        logger.warning("Failed to clear pending record for %s/%s", session_id, job_id, exc_info=True)


def get_previously_applied_urls(user_id: str) -> set[str]:
    """Return set of job URLs the user has already successfully applied to.

    Used at the scoring stage to filter out jobs before they reach the
    application agent — prevents cross-session duplicate applications.
    """
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                SELECT DISTINCT job_url FROM application_results
                WHERE user_id = %s AND status = 'submitted' AND job_url != ''
                """,
                (user_id,),
            )
            return {row[0] for row in cur.fetchall()}
    except Exception:
        logger.warning("Failed to fetch previous applications for user %s", user_id, exc_info=True)
        return set()


def get_rate_limited_companies(
    user_id: str, max_applications: int = 2, window_days: int = 14
) -> set[str]:
    """Return set of company names (lowered) that have hit the rate limit.

    Used at the scoring stage to exclude companies the user has already
    applied to enough times recently.
    """
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                SELECT LOWER(job_company), COUNT(*)
                FROM application_results
                WHERE user_id = %s AND status = 'submitted'
                  AND created_at > NOW() - %s * INTERVAL '1 day'
                  AND job_company != '' AND LOWER(job_company) != 'unknown'
                GROUP BY LOWER(job_company)
                HAVING COUNT(*) >= %s
                """,
                (user_id, window_days, max_applications),
            )
            return {row[0] for row in cur.fetchall()}
    except Exception:
        logger.warning("Failed to fetch rate-limited companies for user %s", user_id, exc_info=True)
        return set()


def check_company_rate_limit(
    company: str,
    user_id: Optional[str] = None,
    max_applications: int = 2,
    window_days: int = 14,
) -> Optional[Dict[str, Any]]:
    """Check if company application rate limit has been reached for this user.

    Returns the most recent application record if limit is exceeded, None if OK.
    Only ``submitted`` status counts. When *user_id* is provided, only checks
    that user's applications to the company.
    """
    try:
        with _connect() as conn:
            if user_id:
                cur = conn.execute(
                    """
                    SELECT COUNT(*), MAX(created_at)
                    FROM application_results
                    WHERE LOWER(job_company) = LOWER(%s)
                      AND user_id = %s
                      AND status = 'submitted'
                      AND created_at > NOW() - %s * INTERVAL '1 day'
                    """,
                    (company, user_id, window_days),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT COUNT(*), MAX(created_at)
                    FROM application_results
                    WHERE LOWER(job_company) = LOWER(%s)
                      AND status = 'submitted'
                      AND created_at > NOW() - %s * INTERVAL '1 day'
                    """,
                    (company, window_days),
                )
            row = cur.fetchone()
            if row and row[0] >= max_applications:
                return {
                    "company": company,
                    "count": row[0],
                    "last_applied_at": row[1].isoformat() if row[1] else None,
                    "window_days": window_days,
                    "max_applications": max_applications,
                }
            return None
    except Exception:
        logger.warning("Failed to check company rate limit for %s", company, exc_info=True)
        return None


def delete_application_results_for_sessions(session_ids: List[str]) -> bool:
    """Delete all application_results for the given session IDs (GDPR deletion).

    Returns True on success, False on error.
    """
    if not session_ids:
        return True
    with _connect() as conn:
        try:
            # Use ANY(%s) with a list parameter for safe IN-clause
            conn.execute(
                "DELETE FROM application_results WHERE session_id = ANY(%s)",
                (session_ids,),
            )
            conn.commit()
            logger.info(
                "Deleted application results for %d sessions", len(session_ids)
            )
            return True
        except Exception:
            conn.rollback()
            logger.exception("Failed to delete application results for sessions")
            return False


def get_results_for_session(session_id: str) -> List[Dict[str, Any]]:
    """Return all application results for a session, ordered by creation time."""
    try:
        with _connect() as conn:
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
    except Exception:
        logger.warning("Failed to get application results for session %s", session_id, exc_info=True)
        return []
