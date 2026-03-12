# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Autopilot runner — checks for due schedules and spawns sessions.

Called by the scheduler every 60 seconds. Constructs a StartSessionRequest
from saved preferences and invokes the same pipeline used by manual sessions.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from croniter import croniter

from backend.shared.autopilot_store import get_due_schedules, get_schedule, mark_run
from backend.shared.config import get_settings
from backend.shared.models.schemas import SessionConfig, StartSessionRequest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HMAC token helpers for email approval links
# ---------------------------------------------------------------------------

def generate_approval_token(schedule_id: str, session_id: str, expires_hours: int = 24) -> str:
    """Create an HMAC token for email approval links."""
    secret = get_settings().NEXTAUTH_SECRET or "fallback-secret"
    expires = int(time.time()) + (expires_hours * 3600)
    message = f"{schedule_id}:{session_id}:{expires}"
    sig = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return f"{expires}:{sig}"


def verify_approval_token(schedule_id: str, session_id: str, token: str) -> bool:
    """Verify an HMAC approval token. Returns False if expired or invalid."""
    secret = get_settings().NEXTAUTH_SECRET or "fallback-secret"
    try:
        expires_str, sig = token.split(":", 1)
        expires = int(expires_str)
    except (ValueError, AttributeError):
        return False

    if time.time() > expires:
        return False

    message = f"{schedule_id}:{session_id}:{expires}"
    expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


# ---------------------------------------------------------------------------
# Compute next run from cron expression
# ---------------------------------------------------------------------------

def compute_next_run(cron_expression: str, tz_name: str = "America/New_York") -> datetime:
    """Return the next UTC datetime for a cron expression in the given timezone."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    cron = croniter(cron_expression, now_local)
    next_local = cron.get_next(datetime)
    return next_local.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Core: check and run due schedules
# ---------------------------------------------------------------------------

async def check_and_run_due_schedules() -> None:
    """Query due autopilot schedules and spawn a session for each.

    This is the coroutine registered with schedule_seconds() in main.py.
    """
    try:
        due = await get_due_schedules()
    except Exception:
        logger.exception("Autopilot: failed to query due schedules")
        return

    if not due:
        return

    logger.info("Autopilot: %d schedule(s) due", len(due))

    # Batch-fetch resume_bytes for all due schedules to avoid N+1 queries
    schedule_ids = [s["id"] for s in due if s.get("resume_bytes") or s.get("resume_filename")]
    resume_bytes_map: Dict[str, Optional[bytes]] = {}
    if schedule_ids:
        try:
            resume_bytes_map = await _batch_get_resume_bytes(schedule_ids)
        except Exception:
            logger.exception("Autopilot: failed to batch-fetch resume bytes")

    for sched in due:
        try:
            await _run_schedule(sched, resume_bytes_map=resume_bytes_map)
        except Exception:
            logger.exception("Autopilot: failed to run schedule %s", sched.get("id"))


async def _run_schedule(
    sched: Dict[str, Any],
    resume_bytes_map: Optional[Dict[str, Optional[bytes]]] = None,
) -> None:
    """Spawn a session for a single autopilot schedule."""
    schedule_id = sched["id"]
    user_id = sched["user_id"]

    logger.info("Autopilot: running schedule %s for user %s", schedule_id, user_id)

    # Check task queue concurrency (max 2 per user)
    try:
        from backend.shared.task_queue import enqueue_session, mark_active
        session_id = str(uuid.uuid4())
        enqueued = await enqueue_session(session_id, user_id)
        if not enqueued:
            logger.warning(
                "Autopilot: user %s at concurrency limit, retrying schedule %s in 15min",
                user_id, schedule_id,
            )
            # Retry in 15 minutes
            retry_at = datetime.now(timezone.utc).replace(
                minute=datetime.now(timezone.utc).minute + 15,
            )
            await mark_run(schedule_id, "", retry_at)
            return
        await mark_active(session_id)
    except Exception:
        logger.debug("Autopilot: task queue unavailable, proceeding anyway", exc_info=True)
        session_id = str(uuid.uuid4())

    # Write resume bytes to temp file if available
    resume_file_path = None
    resume_bytes: Optional[bytes] = None
    ext = ".pdf"

    if sched.get("resume_bytes") or sched.get("resume_filename"):
        # Use batch-fetched bytes if available, fall back to individual fetch
        if resume_bytes_map and schedule_id in resume_bytes_map:
            resume_bytes = resume_bytes_map[schedule_id]
        else:
            resume_bytes = await _get_resume_bytes(schedule_id)
        ext = os.path.splitext(sched.get("resume_filename", "resume.pdf"))[1] or ".pdf"

    # Fallback: pull the user's most recent resume from any prior session
    if not resume_bytes:
        try:
            from backend.shared.resume_store import get_latest_resume_for_user
            result = get_latest_resume_for_user(user_id)
            if result:
                resume_bytes, ext = result
                logger.info("Autopilot: using user's latest resume for schedule %s", schedule_id)
        except Exception:
            logger.debug("Autopilot: failed to fetch user's latest resume", exc_info=True)

    if resume_bytes:
        resume_dir = os.path.join(tempfile.gettempdir(), "jobhunter_resumes")
        os.makedirs(resume_dir, exist_ok=True)
        tmp_path = os.path.join(resume_dir, f"{uuid.uuid4().hex}{ext}")
        with open(tmp_path, "wb") as f:
            f.write(resume_bytes)
        resume_file_path = tmp_path

        # Persist encrypted resume to Postgres keyed by session_id so
        # the /resume-file endpoint can serve it to Skyvern.
        try:
            from backend.shared.resume_crypto import _get_fernet
            from backend.shared.resume_store import save_resume
            enc_data = _get_fernet().encrypt(resume_bytes)
            save_resume(session_id, enc_data, ext)
            logger.info("Autopilot: persisted resume to DB for session %s", session_id)
        except Exception:
            logger.exception("Autopilot: failed to persist resume to DB for session %s", session_id)

    # Build SessionConfig from stored JSON
    session_config = None
    if sched.get("session_config"):
        cfg = sched["session_config"]
        if isinstance(cfg, str):
            import json
            cfg = json.loads(cfg)
        session_config = SessionConfig(**cfg)

    # Build StartSessionRequest
    request_body = StartSessionRequest(
        keywords=sched.get("keywords", []),
        locations=sched.get("locations", ["Remote"]),
        remote_only=sched.get("remote_only", False),
        salary_min=sched.get("salary_min"),
        search_radius=sched.get("search_radius", 100),
        country="US",
        resume_text=sched.get("resume_text"),
        resume_file_path=resume_file_path,
        linkedin_url=sched.get("linkedin_url"),
        preferences={
            **(sched.get("preferences") or {}),
            "_autopilot_schedule_id": schedule_id,
            "_autopilot_auto_approve": sched.get("auto_approve", False),
        },
        config=session_config,
    )

    # Register session in the session registry and DB (same as manual flow)
    from backend.gateway.routes.sessions import (
        _run_pipeline,
        _spawn_background,
        event_logs,
        session_registry,
        sse_subscribers,
    )
    from backend.shared.session_store import upsert_session

    event_logs[session_id] = []
    sse_subscribers[session_id] = []

    session_meta = {
        "session_id": session_id,
        "user_id": user_id,
        "status": "intake",
        "keywords": request_body.keywords,
        "locations": request_body.locations,
        "remote_only": request_body.remote_only,
        "salary_min": request_body.salary_min,
        "resume_text_snippet": (request_body.resume_text or "")[:200],
        "linkedin_url": request_body.linkedin_url,
        "applications_submitted": 0,
        "applications_failed": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "autopilot_schedule_id": schedule_id,
    }
    session_registry[session_id] = session_meta
    upsert_session(session_id, session_meta)

    # Get the LangGraph instance from the app state
    # Import lazily to avoid circular imports
    from backend.gateway.main import _app_ref
    graph = _app_ref.state.graph if _app_ref else None
    if graph is None:
        logger.error("Autopilot: no graph available, cannot run schedule %s", schedule_id)
        return

    # Launch pipeline in background
    _spawn_background(_run_pipeline(session_id, request_body, graph, user_id=user_id))

    # Compute next run and update schedule
    next_run = compute_next_run(
        sched["cron_expression"],
        sched.get("timezone", "America/New_York"),
    )
    await mark_run(schedule_id, session_id, next_run)

    logger.info(
        "Autopilot: spawned session %s for schedule %s, next run %s",
        session_id, schedule_id, next_run.isoformat(),
    )

    # Send notification if not auto-approve
    if not sched.get("auto_approve", False):
        notification_email = sched.get("notification_email")
        if not notification_email:
            # Look up user email
            from backend.shared.billing_store import get_user_by_id
            user = await _get_user_email(user_id)
            notification_email = user

        if notification_email:
            try:
                from backend.shared.email_notifications import send_autopilot_started_email
                await send_autopilot_started_email(
                    to_email=notification_email,
                    session_id=session_id,
                    schedule_name=sched.get("name", "My Job Search"),
                    keywords=sched.get("keywords", []),
                )
            except Exception:
                logger.exception("Autopilot: failed to send notification email")


async def _batch_get_resume_bytes(schedule_ids: list[str]) -> Dict[str, Optional[bytes]]:
    """Batch fetch resume_bytes for multiple schedules in one query."""
    import asyncio
    from backend.shared.db import get_connection

    def _fetch():
        with get_connection() as conn:
            placeholders = ",".join(["%s"] * len(schedule_ids))
            cur = conn.execute(
                f"SELECT id, resume_bytes FROM autopilot_schedules WHERE id IN ({placeholders})",
                schedule_ids,
            )
            return {
                str(row[0]): (bytes(row[1]) if isinstance(row[1], memoryview) else row[1]) if row[1] else None
                for row in cur.fetchall()
            }

    return await asyncio.to_thread(_fetch)


async def _get_resume_bytes(schedule_id: str) -> Optional[bytes]:
    """Fetch resume_bytes from DB (not returned by default _row_to_dict)."""
    import asyncio
    from backend.shared.db import get_connection

    def _fetch():
        with get_connection() as conn:
            row = conn.execute(
                "SELECT resume_bytes FROM autopilot_schedules WHERE id = %s",
                (schedule_id,),
            ).fetchone()
            if row and row[0]:
                return bytes(row[0]) if isinstance(row[0], memoryview) else row[0]
            return None

    return await asyncio.to_thread(_fetch)


async def _get_user_email(user_id: str) -> Optional[str]:
    """Look up a user's email by their ID."""
    import asyncio
    from backend.shared.db import get_connection

    def _fetch():
        with get_connection() as conn:
            row = conn.execute(
                "SELECT email FROM users WHERE id = %s",
                (user_id,),
            ).fetchone()
            return row[0] if row else None

    return await asyncio.to_thread(_fetch)
