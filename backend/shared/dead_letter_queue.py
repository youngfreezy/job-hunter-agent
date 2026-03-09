# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Dead letter queue for failed job applications.

Captures failed application attempts so they can be reviewed, debugged,
and optionally retried. The dead_letter_queue table was created by Alembic
migration d9617b97a43d.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from backend.shared.db import get_connection

logger = logging.getLogger(__name__)


def _connect():
    return get_connection()


def enqueue_failed_application(
    session_id: str,
    user_id: str,
    job_id: str,
    job_title: str = "",
    job_company: str = "",
    job_url: str = "",
    job_board: str = "",
    error_message: str = "",
    error_type: str = "unknown",
    payload: Optional[Dict[str, Any]] = None,
    retry_delay_minutes: int = 30,
) -> None:
    """Add a failed application to the dead letter queue."""
    with _connect() as conn:
        try:
            retry_after = datetime.now(timezone.utc) + timedelta(minutes=retry_delay_minutes)
            conn.execute(
                """
                INSERT INTO dead_letter_queue
                    (session_id, user_id, job_id, job_title, job_company, job_url,
                     job_board, error_message, error_type, payload, retry_after)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id, user_id, job_id, job_title, job_company, job_url,
                    job_board, error_message, error_type,
                    json.dumps(payload) if payload else None,
                    retry_after,
                ),
            )
            conn.commit()
            logger.info("DLQ: enqueued failed application %s (%s)", job_id, error_type)
        except Exception:
            conn.rollback()
            logger.debug("Failed to enqueue to DLQ", exc_info=True)


def get_pending_items(
    user_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Get pending DLQ items, optionally filtered by user."""
    with _connect() as conn:
        try:
            if user_id:
                cur = conn.execute(
                    """SELECT id, session_id, user_id, job_id, job_title, job_company,
                              job_url, job_board, error_message, error_type,
                              attempt_count, created_at, retry_after
                       FROM dead_letter_queue
                       WHERE user_id = %s AND status = 'pending'
                       ORDER BY created_at DESC
                       LIMIT %s""",
                    (user_id, limit),
                )
            else:
                cur = conn.execute(
                    """SELECT id, session_id, user_id, job_id, job_title, job_company,
                              job_url, job_board, error_message, error_type,
                              attempt_count, created_at, retry_after
                       FROM dead_letter_queue
                       WHERE status = 'pending'
                       ORDER BY created_at DESC
                       LIMIT %s""",
                    (limit,),
                )
            return [
                {
                    "id": r[0],
                    "session_id": r[1],
                    "user_id": r[2],
                    "job_id": r[3],
                    "job_title": r[4] or "",
                    "job_company": r[5] or "",
                    "job_url": r[6] or "",
                    "job_board": r[7] or "",
                    "error_message": r[8] or "",
                    "error_type": r[9] or "",
                    "attempt_count": r[10],
                    "created_at": r[11].isoformat() if r[11] else None,
                    "retry_after": r[12].isoformat() if r[12] else None,
                }
                for r in cur.fetchall()
            ]
        except Exception:
            logger.debug("Failed to get DLQ items", exc_info=True)
            return []


def mark_resolved(dlq_id: int, resolution: str = "resolved") -> None:
    """Mark a DLQ item as resolved (retried successfully, or dismissed)."""
    with _connect() as conn:
        try:
            conn.execute(
                """UPDATE dead_letter_queue
                   SET status = %s, resolved_at = NOW()
                   WHERE id = %s""",
                (resolution, dlq_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.debug("Failed to resolve DLQ item %d", dlq_id, exc_info=True)


def increment_attempt(dlq_id: int, retry_delay_minutes: int = 60) -> None:
    """Increment the attempt count and push back the retry_after time."""
    with _connect() as conn:
        try:
            retry_after = datetime.now(timezone.utc) + timedelta(minutes=retry_delay_minutes)
            conn.execute(
                """UPDATE dead_letter_queue
                   SET attempt_count = attempt_count + 1,
                       retry_after = %s
                   WHERE id = %s""",
                (retry_after, dlq_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.debug("Failed to increment DLQ attempt for %d", dlq_id, exc_info=True)


def delete_for_sessions(session_ids: List[str]) -> bool:
    """Delete DLQ entries for given session IDs (GDPR)."""
    if not session_ids:
        return True
    with _connect() as conn:
        try:
            conn.execute(
                "DELETE FROM dead_letter_queue WHERE session_id = ANY(%s)",
                (session_ids,),
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            logger.debug("Failed to delete DLQ entries", exc_info=True)
            return False
