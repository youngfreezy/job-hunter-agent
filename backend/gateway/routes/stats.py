# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Lifetime stats endpoint for time-savings marketing."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from backend.gateway.deps import get_current_user
from backend.shared.db import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stats", tags=["stats"])

MANUAL_MINUTES_PER_APP = 60  # HR Dive + BLS benchmark


def _connect():
    return get_connection()


@router.get("/lifetime")
async def get_lifetime_stats(request: Request):
    """Aggregate lifetime stats for the authenticated user."""
    user = get_current_user(request)
    user_id = user["id"]

    with _connect() as conn:
        try:
            # Get session-level aggregates
            cur = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_sessions,
                    COALESCE(SUM(applications_submitted), 0) AS total_submitted,
                    COALESCE(SUM(applications_failed), 0) AS total_failed
                FROM sessions
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            total_sessions = row[0]
            total_submitted = row[1]
            total_failed = row[2]

            # Get application-level aggregates (duration + avg fit)
            cur2 = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_applications,
                    COALESCE(SUM(duration_seconds), 0) AS total_duration_seconds
                FROM application_results ar
                JOIN sessions s ON ar.session_id = s.id
                WHERE s.user_id = %s
                """,
                (user_id,),
            )
            row2 = cur2.fetchone()
            total_applications = row2[0]
            total_duration_seconds = row2[1]

            # Time saved: (submitted apps * 60 min) - actual automation time
            manual_estimate_minutes = total_submitted * MANUAL_MINUTES_PER_APP
            automation_minutes = total_duration_seconds / 60
            time_saved_minutes = max(0, manual_estimate_minutes - automation_minutes)

            return {
                "total_sessions": total_sessions,
                "total_submitted": total_submitted,
                "total_failed": total_failed,
                "total_applications": total_applications,
                "manual_estimate_minutes": round(manual_estimate_minutes, 1),
                "automation_minutes": round(automation_minutes, 1),
                "time_saved_minutes": round(time_saved_minutes, 1),
                "time_saved_hours": round(time_saved_minutes / 60, 1),
            }
        except Exception:
            logger.exception("Failed to compute lifetime stats for user %s", user_id)
            return {
                "total_sessions": 0,
                "total_submitted": 0,
                "total_failed": 0,
                "total_applications": 0,
                "manual_estimate_minutes": 0,
                "automation_minutes": 0,
                "time_saved_minutes": 0,
                "time_saved_hours": 0,
            }
