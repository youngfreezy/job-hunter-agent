# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Summarize submission evidence already validated by the application adapters."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import ApplicationResult, ApplicationStatus

logger = logging.getLogger(__name__)


def count_verified_results(applications: Sequence[ApplicationResult]) -> tuple[int, int]:
    """Count confirmed statuses without inventing new evidence or changing outcomes.

    Browser adapters only emit SUBMITTED after a receipt; uncertain delivery stays
    FAILED. This stage summarizes those outcomes, it cannot independently infer a
    receipt from screenshots or upgrade an uncertain attempt to success.
    """
    verified = sum(app.status == ApplicationStatus.SUBMITTED for app in applications)
    return verified, len(applications) - verified


async def run_verification_agent(state: JobHunterState) -> dict:
    """Report confirmed adapter results without model inference or browser actions."""
    applications = state.get("applications_submitted") or []
    if not applications:
        return {
            "agent_statuses": {"verification": "completed -- no applications to verify"},
            "errors": [],
        }

    session_id = state.get("session_id", "")
    try:
        await emit_agent_event(session_id, "verification_progress", {
            "step": f"Checking {len(applications)} submitted {'application' if len(applications) == 1 else 'applications'}...",
            "progress": 0,
            "current": 0,
            "total": len(applications),
        })
        verified, failed = count_verified_results(applications)
        agent_status = (
            f"completed -- {verified} verified, {failed} failed. "
            "Counts reflect submission evidence recorded by the application adapters."
        )
        logger.info("Verification complete: %d verified, %d failed", verified, failed)
        await emit_agent_event(session_id, "verification_progress", {
            "step": f"Done — {verified} confirmed, {failed} need attention",
            "progress": 100,
            "current": len(applications),
            "total": len(applications),
        })
    except Exception:
        logger.exception("Verification agent failed")
        return {
            "agent_statuses": {"verification": "failed -- could not summarize application results"},
            "errors": ["Verification agent could not summarize application results."],
        }
    return {"agent_statuses": {"verification": agent_status}, "errors": []}


run = run_verification_agent
