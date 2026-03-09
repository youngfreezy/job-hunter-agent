# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Persistent storage for autopilot schedules.

Follows the billing_store.py pattern: sync psycopg for DDL,
async helpers for CRUD via asyncio.to_thread.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.shared.config import get_settings
from backend.shared.db import get_connection

logger = logging.getLogger(__name__)

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS autopilot_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    name TEXT NOT NULL DEFAULT 'My Job Search',

    -- Saved search preferences
    keywords JSONB NOT NULL DEFAULT '[]',
    locations JSONB NOT NULL DEFAULT '["Remote"]',
    remote_only BOOLEAN DEFAULT FALSE,
    salary_min INT,
    search_radius INT DEFAULT 100,
    resume_text TEXT,
    resume_bytes BYTEA,
    resume_filename TEXT,
    linkedin_url TEXT,
    preferences JSONB DEFAULT '{}',
    session_config JSONB,

    -- Schedule
    cron_expression TEXT NOT NULL DEFAULT '0 8 * * 1-5',
    timezone TEXT DEFAULT 'America/New_York',
    is_active BOOLEAN DEFAULT TRUE,

    -- Approval settings
    auto_approve BOOLEAN DEFAULT FALSE,
    notification_email TEXT,

    -- Runtime metadata
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    last_session_id TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_autopilot_user ON autopilot_schedules(user_id);
CREATE INDEX IF NOT EXISTS idx_autopilot_next_run ON autopilot_schedules(next_run_at)
    WHERE is_active = TRUE;
"""


def _connect():
    return get_connection()


async def ensure_autopilot_tables() -> None:
    """Create autopilot_schedules table if it doesn't exist."""
    import asyncio

    def _create():
        with _connect() as conn:
            conn.execute(_CREATE_TABLES)
            conn.commit()

    await asyncio.to_thread(_create)
    logger.info("autopilot_schedules table ensured")


# ---------------------------------------------------------------------------
# CRUD helpers (all async via to_thread)
# ---------------------------------------------------------------------------

async def create_schedule(
    user_id: str,
    *,
    name: str = "My Job Search",
    keywords: List[str],
    locations: List[str],
    remote_only: bool = False,
    salary_min: Optional[int] = None,
    search_radius: int = 100,
    resume_text: Optional[str] = None,
    resume_bytes: Optional[bytes] = None,
    resume_filename: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    preferences: Optional[Dict[str, Any]] = None,
    session_config: Optional[Dict[str, Any]] = None,
    cron_expression: str = "0 8 * * 1-5",
    tz: str = "America/New_York",
    auto_approve: bool = False,
    notification_email: Optional[str] = None,
    next_run_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    import asyncio

    # Enforce per-user schedule quota
    existing = await list_schedules(user_id)
    if len(existing) >= MAX_SCHEDULES_PER_USER:
        raise ValueError(
            f"Maximum {MAX_SCHEDULES_PER_USER} autopilot schedules per user"
        )

    schedule_id = str(uuid.uuid4())

    def _insert():
        with _connect() as conn:
            row = conn.execute(
                """
                INSERT INTO autopilot_schedules
                    (id, user_id, name, keywords, locations, remote_only,
                     salary_min, search_radius, resume_text, resume_bytes,
                     resume_filename, linkedin_url, preferences, session_config,
                     cron_expression, timezone, auto_approve, notification_email,
                     next_run_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    schedule_id,
                    user_id,
                    name,
                    json.dumps(keywords),
                    json.dumps(locations),
                    remote_only,
                    salary_min,
                    search_radius,
                    resume_text,
                    resume_bytes,
                    resume_filename,
                    linkedin_url,
                    json.dumps(preferences or {}),
                    json.dumps(session_config) if session_config else None,
                    cron_expression,
                    tz,
                    auto_approve,
                    notification_email,
                    next_run_at,
                ),
            ).fetchone()
            conn.commit()
            return _row_to_dict(row, conn.description)

    return await asyncio.to_thread(_insert)


async def get_schedule(schedule_id: str) -> Optional[Dict[str, Any]]:
    import asyncio

    def _get():
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM autopilot_schedules WHERE id = %s",
                (schedule_id,),
            ).fetchone()
            return _row_to_dict(row, conn.description) if row else None

    return await asyncio.to_thread(_get)


async def list_schedules(user_id: str) -> List[Dict[str, Any]]:
    import asyncio

    def _list():
        with _connect() as conn:
            cur = conn.execute(
                "SELECT * FROM autopilot_schedules WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,),
            )
            return [_row_to_dict(r, cur.description) for r in cur.fetchall()]

    return await asyncio.to_thread(_list)


async def update_schedule(schedule_id: str, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update allowed fields on a schedule owned by user_id."""
    import asyncio

    allowed = {
        "name", "keywords", "locations", "remote_only", "salary_min",
        "search_radius", "resume_text", "resume_bytes", "resume_filename",
        "linkedin_url", "preferences", "session_config", "cron_expression",
        "timezone", "auto_approve", "notification_email", "is_active",
        "next_run_at",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        return await get_schedule(schedule_id)

    # JSON-encode JSONB fields
    for key in ("keywords", "locations", "preferences", "session_config"):
        if key in filtered and not isinstance(filtered[key], str):
            filtered[key] = json.dumps(filtered[key])

    filtered["updated_at"] = datetime.now(timezone.utc)

    set_clauses = ", ".join(f"{k} = %s" for k in filtered)
    values = list(filtered.values())

    def _update():
        with _connect() as conn:
            row = conn.execute(
                f"UPDATE autopilot_schedules SET {set_clauses} WHERE id = %s AND user_id = %s RETURNING *",
                values + [schedule_id, user_id],
            ).fetchone()
            conn.commit()
            return _row_to_dict(row, conn.description) if row else None

    return await asyncio.to_thread(_update)


async def delete_schedule(schedule_id: str, user_id: str) -> bool:
    import asyncio

    def _delete():
        with _connect() as conn:
            cur = conn.execute(
                "DELETE FROM autopilot_schedules WHERE id = %s AND user_id = %s",
                (schedule_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0

    return await asyncio.to_thread(_delete)


async def get_due_schedules() -> List[Dict[str, Any]]:
    """Return all active schedules whose next_run_at is in the past."""
    import asyncio

    def _query():
        with _connect() as conn:
            cur = conn.execute(
                """
                SELECT * FROM autopilot_schedules
                WHERE is_active = TRUE
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= NOW()
                ORDER BY next_run_at ASC
                """,
            )
            return [_row_to_dict(r, cur.description) for r in cur.fetchall()]

    return await asyncio.to_thread(_query)


async def mark_run(schedule_id: str, session_id: str, next_run_at: datetime) -> None:
    """Update last_run_at, last_session_id, and next_run_at after a run."""
    import asyncio

    def _mark():
        with _connect() as conn:
            conn.execute(
                """
                UPDATE autopilot_schedules
                SET last_run_at = NOW(),
                    last_session_id = %s,
                    next_run_at = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (session_id, next_run_at, schedule_id),
            )
            conn.commit()

    await asyncio.to_thread(_mark)


MAX_SCHEDULES_PER_USER: int = 5


def delete_all_user_schedules(user_id: str) -> bool:
    """Delete all autopilot schedules for a user (GDPR)."""
    with _connect() as conn:
        try:
            conn.execute(
                "DELETE FROM autopilot_schedules WHERE user_id = %s",
                (user_id,),
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            logger.error("Failed to delete autopilot schedules for user %s", user_id, exc_info=True)
            return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row, description) -> Dict[str, Any]:
    if row is None:
        return {}
    cols = [d.name for d in description]
    result = dict(zip(cols, row))
    # Convert UUIDs and datetimes to strings for JSON serialization
    for k, v in result.items():
        if isinstance(v, uuid.UUID):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, memoryview):
            result[k] = bytes(v)
        elif isinstance(v, bytes) and k != "resume_bytes":
            result[k] = v.decode("utf-8", errors="replace")
    # Don't include resume_bytes in serialized output (too large)
    result.pop("resume_bytes", None)
    return result
