# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Autopilot REST API — manage scheduled job search sessions."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.shared.autopilot_runner import (
    compute_next_run,
    generate_approval_token,
    verify_approval_token,
)
from backend.shared.autopilot_store import (
    create_schedule,
    delete_schedule,
    get_schedule,
    list_schedules,
    update_schedule,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autopilot", tags=["autopilot"])


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class CreateScheduleRequest(BaseModel):
    name: str = "My Job Search"
    keywords: List[str]
    locations: List[str] = Field(default_factory=lambda: ["Remote"])
    remote_only: bool = False
    salary_min: Optional[int] = None
    search_radius: int = 100
    resume_text: Optional[str] = None
    linkedin_url: Optional[str] = None
    preferences: Dict[str, Any] = Field(default_factory=dict)
    session_config: Optional[Dict[str, Any]] = None
    cron_expression: str = "0 8 * * 1-5"
    timezone: str = "America/New_York"
    auto_approve: bool = False
    notification_email: Optional[str] = None


class UpdateScheduleRequest(BaseModel):
    name: Optional[str] = None
    keywords: Optional[List[str]] = None
    locations: Optional[List[str]] = None
    remote_only: Optional[bool] = None
    salary_min: Optional[int] = None
    search_radius: Optional[int] = None
    resume_text: Optional[str] = None
    linkedin_url: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None
    session_config: Optional[Dict[str, Any]] = None
    cron_expression: Optional[str] = None
    timezone: Optional[str] = None
    auto_approve: Optional[bool] = None
    notification_email: Optional[str] = None


# ---------------------------------------------------------------------------
# CRUD endpoints (JWT-authenticated)
# ---------------------------------------------------------------------------

@router.post("/schedules")
async def create_autopilot_schedule(body: CreateScheduleRequest, request: Request):
    from backend.gateway.deps import get_current_user
    user = get_current_user(request)
    user_id = user["id"]

    # Validate cron expression
    try:
        from croniter import croniter
        croniter(body.cron_expression)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid cron expression: {e}")

    next_run = compute_next_run(body.cron_expression, body.timezone)

    try:
        schedule = await create_schedule(
            user_id=user_id,
            name=body.name,
            keywords=body.keywords,
            locations=body.locations,
            remote_only=body.remote_only,
            salary_min=body.salary_min,
            search_radius=body.search_radius,
            resume_text=body.resume_text,
            linkedin_url=body.linkedin_url,
            preferences=body.preferences,
            session_config=body.session_config,
            cron_expression=body.cron_expression,
            tz=body.timezone,
            auto_approve=body.auto_approve,
            notification_email=body.notification_email,
            next_run_at=next_run,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return schedule


@router.get("/schedules")
async def list_autopilot_schedules(request: Request):
    from backend.gateway.deps import get_current_user
    user = get_current_user(request)
    return await list_schedules(user["id"])


@router.get("/schedules/{schedule_id}")
async def get_autopilot_schedule(schedule_id: str, request: Request):
    from backend.gateway.deps import get_current_user
    user = get_current_user(request)

    schedule = await get_schedule(schedule_id)
    if not schedule or schedule.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.put("/schedules/{schedule_id}")
async def update_autopilot_schedule(
    schedule_id: str, body: UpdateScheduleRequest, request: Request
):
    from backend.gateway.deps import get_current_user
    user = get_current_user(request)

    updates = body.model_dump(exclude_none=True)

    # Validate cron if being updated
    if "cron_expression" in updates:
        try:
            from croniter import croniter
            croniter(updates["cron_expression"])
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=400, detail=f"Invalid cron expression: {e}")
        # Recompute next_run
        tz = updates.get("timezone")
        if not tz:
            existing = await get_schedule(schedule_id)
            tz = (existing or {}).get("timezone", "America/New_York")
        updates["next_run_at"] = compute_next_run(updates["cron_expression"], tz)

    result = await update_schedule(schedule_id, user["id"], updates)
    if not result:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return result


@router.delete("/schedules/{schedule_id}")
async def delete_autopilot_schedule(schedule_id: str, request: Request):
    from backend.gateway.deps import get_current_user
    user = get_current_user(request)

    deleted = await delete_schedule(schedule_id, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"deleted": True}


@router.post("/schedules/{schedule_id}/pause")
async def toggle_pause(schedule_id: str, request: Request):
    from backend.gateway.deps import get_current_user
    user = get_current_user(request)

    schedule = await get_schedule(schedule_id)
    if not schedule or schedule.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Schedule not found")

    new_active = not schedule.get("is_active", True)
    updates: Dict[str, Any] = {"is_active": new_active}

    # Recompute next_run when resuming
    if new_active:
        updates["next_run_at"] = compute_next_run(
            schedule["cron_expression"],
            schedule.get("timezone", "America/New_York"),
        )

    result = await update_schedule(schedule_id, user["id"], updates)
    return result


@router.post("/schedules/{schedule_id}/run-now")
async def run_now(schedule_id: str, request: Request):
    """Trigger an immediate autopilot run for this schedule."""
    from backend.gateway.deps import get_current_user
    user = get_current_user(request)

    schedule = await get_schedule(schedule_id)
    if not schedule or schedule.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Schedule not found")

    from backend.shared.autopilot_runner import _run_schedule
    # Fetch full schedule with resume_bytes possibility
    await _run_schedule(schedule)

    return {"triggered": True, "schedule_id": schedule_id}


# ---------------------------------------------------------------------------
# Email approval endpoint (HMAC-authenticated, no JWT required)
# ---------------------------------------------------------------------------

@router.get("/approve/{schedule_id}/{session_id}")
async def approve_autopilot_session(
    schedule_id: str,
    session_id: str,
    token: str = Query(...),
    action: str = Query(default="approve"),  # approve, skip
):
    """Handle email approval/skip links. HMAC-verified, no JWT needed."""
    if not verify_approval_token(schedule_id, session_id, token):
        raise HTTPException(status_code=403, detail="Invalid or expired approval link")

    if action == "skip":
        # Mark session as skipped/cancelled
        from backend.gateway.routes.sessions import _set_session_status, session_registry
        if session_id in session_registry:
            _set_session_status(session_id, "failed")
        return {"status": "skipped", "session_id": session_id}

    # Approve: resume the pipeline past the shortlist review gate
    from backend.gateway.routes.sessions import session_registry
    session = session_registry.get(session_id, {})
    status = session.get("status", "")

    if status == "awaiting_review":
        # Auto-approve all jobs in the shortlist
        from backend.gateway.routes.sessions import _resume_pipeline, _spawn_background
        from backend.gateway.main import _app_ref
        graph = _app_ref.state.graph if _app_ref else None
        if graph:
            _spawn_background(_resume_pipeline(
                session_id,
                graph,
                resume_value={"approved": True, "approved_job_ids": "all"},
            ))
            return {"status": "approved", "session_id": session_id}

    return {
        "status": "pending",
        "message": "Session is not yet ready for approval. Check back shortly or view in dashboard.",
        "session_id": session_id,
    }
