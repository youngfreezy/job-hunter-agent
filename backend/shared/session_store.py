# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Persistent session metadata storage in Postgres.

Replaces the in-memory session_registry dict so session metadata survives
backend restarts. The sessions table was created by Alembic migration
d9617b97a43d.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.shared.db import get_connection

logger = logging.getLogger(__name__)


def _connect():
    return get_connection()


def upsert_session(session_id: str, data: Dict[str, Any]) -> None:
    """Insert or update session metadata."""
    with _connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO sessions (id, user_id, status, keywords, locations,
                                      remote_only, salary_min, resume_text_snippet,
                                      linkedin_url, applications_submitted,
                                      applications_failed, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    applications_submitted = EXCLUDED.applications_submitted,
                    applications_failed = EXCLUDED.applications_failed,
                    updated_at = NOW()
                """,
                (
                    session_id,
                    data["user_id"],
                    data.get("status", "intake"),
                    json.dumps(data.get("keywords", [])),
                    json.dumps(data.get("locations", [])),
                    data.get("remote_only", False),
                    data.get("salary_min"),
                    data.get("resume_text_snippet", ""),
                    data.get("linkedin_url"),
                    data.get("applications_submitted", 0),
                    data.get("applications_failed", 0),
                    data.get("created_at", datetime.now(timezone.utc).isoformat()),
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.error("Failed to upsert session %s", session_id, exc_info=True)


def update_session_status(session_id: str, status: str) -> None:
    """Update just the status field for a session."""
    with _connect() as conn:
        try:
            conn.execute(
                "UPDATE sessions SET status = %s, updated_at = NOW() WHERE id = %s",
                (status, session_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.error("Failed to update session status %s", session_id, exc_info=True)


def update_session_counts(
    session_id: str,
    applications_submitted: int,
    applications_failed: int,
) -> None:
    """Update application counts for a session."""
    with _connect() as conn:
        try:
            conn.execute(
                """UPDATE sessions
                   SET applications_submitted = %s,
                       applications_failed = %s,
                       updated_at = NOW()
                   WHERE id = %s""",
                (applications_submitted, applications_failed, session_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.error("Failed to update session counts %s", session_id, exc_info=True)


def get_sessions_for_user(user_id: str) -> List[Dict[str, Any]]:
    """Load all sessions for a user from Postgres."""
    with _connect() as conn:
        try:
            cur = conn.execute(
                """SELECT id, user_id, status, keywords, locations, remote_only,
                          salary_min, resume_text_snippet, linkedin_url,
                          applications_submitted, applications_failed, created_at
                   FROM sessions
                   WHERE user_id = %s
                   ORDER BY created_at DESC""",
                (user_id,),
            )
            rows = cur.fetchall()
            return [
                {
                    "session_id": r[0],
                    "user_id": r[1],
                    "status": r[2],
                    "keywords": json.loads(r[3]) if r[3] else [],
                    "locations": json.loads(r[4]) if r[4] else [],
                    "remote_only": r[5],
                    "salary_min": r[6],
                    "resume_text_snippet": r[7] or "",
                    "linkedin_url": r[8],
                    "applications_submitted": r[9] or 0,
                    "applications_failed": r[10] or 0,
                    "created_at": r[11].isoformat() if r[11] else "",
                }
                for r in rows
            ]
        except Exception:
            logger.warning("Failed to load sessions for user %s", user_id, exc_info=True)
            return []


def get_interrupted_sessions(max_age_hours: int = 2) -> List[Dict[str, Any]]:
    """Find sessions stuck in running/non-terminal states (orphaned by restart).

    Only returns sessions updated within the last ``max_age_hours`` to avoid
    resuming ancient stale sessions.
    """
    with _connect() as conn:
        try:
            cur = conn.execute(
                """SELECT id, user_id, status
                   FROM sessions
                   WHERE status IN ('intake', 'coaching', 'discovering', 'scoring',
                                    'tailoring', 'applying', 'running', 'interrupted')
                     AND updated_at >= NOW() - INTERVAL '%s hours'
                   ORDER BY created_at DESC""",
                (max_age_hours,),
            )
            return [{"session_id": r[0], "user_id": r[1], "status": r[2]} for r in cur.fetchall()]
        except Exception:
            logger.warning("Failed to query interrupted sessions", exc_info=True)
            return []


def mark_sessions_interrupted(session_ids: List[str]) -> None:
    """Bulk-mark sessions as interrupted (called on SIGTERM)."""
    if not session_ids:
        return
    with _connect() as conn:
        try:
            conn.execute(
                "UPDATE sessions SET status = 'interrupted', updated_at = NOW() WHERE id = ANY(%s)",
                (session_ids,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.error("Failed to mark sessions interrupted", exc_info=True)


def cleanup_old_data(days: int = 90) -> int:
    """Delete application results and sessions older than N days. Returns count deleted."""
    with _connect() as conn:
        try:
            # Delete old application results (keep sessions table for reference)
            cur = conn.execute(
                "DELETE FROM application_results WHERE created_at < NOW() - INTERVAL '%s days'",
                (days,),
            )
            app_count = cur.rowcount

            # Delete resolved DLQ items older than 30 days
            cur = conn.execute(
                "DELETE FROM dead_letter_queue WHERE status != 'pending' AND created_at < NOW() - INTERVAL '30 days'"
            )
            dlq_count = cur.rowcount

            conn.commit()
            logger.info("Cleanup: deleted %d old app results, %d old DLQ items", app_count, dlq_count)
            return app_count + dlq_count
        except Exception:
            conn.rollback()
            logger.error("Cleanup failed", exc_info=True)
            return 0


def delete_sessions_for_user(user_id: str) -> bool:
    """Delete all sessions for a user (GDPR)."""
    with _connect() as conn:
        try:
            conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            logger.error("Failed to delete sessions for user %s", user_id, exc_info=True)
            return False
