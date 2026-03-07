"""Graph-authoritative workflow supervisor for steering-aware control."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage

from backend.orchestrator.agents._login_sync import signal_login_complete
from backend.orchestrator.agents.steering_judge import (
    SteeringDirective,
    SteeringJudgeResult,
    judge as judge_steering,
)
from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.event_bus import emit_agent_event


def _build_recent_events(state: JobHunterState) -> List[Dict[str, Any]]:
    return [
        {
            "status": state.get("status"),
            "agent_statuses": state.get("agent_statuses", {}),
            "current_application": state.get("current_application"),
            "applications_submitted": len(state.get("applications_submitted") or []),
            "applications_failed": len(state.get("applications_failed") or []),
            "applications_skipped": len(state.get("applications_skipped") or []),
            "errors": (state.get("errors") or [])[-3:],
        }
    ]


def _build_session_snapshot(state: JobHunterState) -> Dict[str, Any]:
    return {
        "session_id": state.get("session_id"),
        "status": state.get("status"),
        "keywords": state.get("keywords", []),
        "locations": state.get("locations", []),
        "current_application": state.get("current_application"),
        "application_queue_size": len(state.get("application_queue") or []),
        "agent_statuses": state.get("agent_statuses", {}),
        "discovered_jobs": len(state.get("discovered_jobs") or []),
        "scored_jobs": len(state.get("scored_jobs") or []),
        "submitted": len(state.get("applications_submitted") or []),
        "failed": len(state.get("applications_failed") or []),
        "skipped": len(state.get("applications_skipped") or []),
        "pause_requested": state.get("pause_requested", False),
    }


async def preview_steering_message(
    state: JobHunterState,
    user_message: str,
) -> SteeringJudgeResult:
    """Return the supervisor's response for a user message without mutating state."""
    return await judge_steering(
        user_message=user_message,
        session_snapshot=_build_session_snapshot(state),
        recent_events=_build_recent_events(state),
    )


async def _signal_resume_intervention(session_id: str) -> None:
    try:
        import redis.asyncio as aioredis

        from backend.shared.config import get_settings

        settings = get_settings()
        redis_client = aioredis.from_url(settings.REDIS_URL)
        try:
            await redis_client.set(f"intervention:resume:{session_id}", "1", ex=600)
        finally:
            await redis_client.close()
    except Exception:
        # The explicit resume endpoint remains the hard guarantee.
        pass


def _directive_dicts(result: SteeringJudgeResult) -> List[Dict[str, Any]]:
    return [directive.model_dump() for directive in result.directives]


async def apply_supervision_result(
    state: JobHunterState,
    result: SteeringJudgeResult,
    *,
    processed_count: int,
    continue_to: Optional[str],
) -> Dict[str, Any]:
    """Translate a judged steering result into graph state updates and side effects."""
    updates: Dict[str, Any] = {
        "steering_messages_processed": processed_count,
        "pending_supervisor_response": result.response_message,
        "pending_supervisor_directives": _directive_dicts(result),
        "messages": [AIMessage(content=result.response_message)],
    }

    pause_requested = state.get("pause_requested", False)
    status_before_pause = state.get("status_before_pause")

    for directive in result.directives:
        if directive.action == "set_mode" and directive.mode:
            updates["steering_mode"] = directive.mode
        elif directive.action == "pause":
            if not pause_requested:
                status_before_pause = state.get("status")
            updates["pause_requested"] = True
            updates["status"] = "paused"
            updates["status_before_pause"] = status_before_pause
            updates["pause_resume_node"] = continue_to or state.get("pause_resume_node")
            pause_requested = True
        elif directive.action == "resume_workflow":
            updates["pause_requested"] = False
            updates["status"] = status_before_pause or state.get("status") or "applying"
            updates["status_before_pause"] = None
            pause_requested = False
        elif directive.action == "skip_next_job":
            updates["skip_next_job_requested"] = True
        elif directive.action == "resume_intervention":
            await _signal_resume_intervention(state.get("session_id", ""))
        elif directive.action == "confirm_login":
            signal_login_complete(state.get("session_id", ""))

    await emit_agent_event(
        state.get("session_id", ""),
        "status",
        {
            "status": "steering",
            "message": result.response_message,
            "directives": _directive_dicts(result),
        },
    )
    return updates


async def run_workflow_supervisor(
    state: JobHunterState,
    *,
    continue_to: Optional[str],
) -> Dict[str, Any]:
    """Evaluate pending steering messages and persist the authoritative control result."""
    human_messages = state.get("human_messages") or []
    processed = state.get("steering_messages_processed", 0)
    if len(human_messages) <= processed:
        return {}

    latest_message = human_messages[-1]
    result = await preview_steering_message(state, latest_message)
    return await apply_supervision_result(
        state,
        result,
        processed_count=len(human_messages),
        continue_to=continue_to,
    )
