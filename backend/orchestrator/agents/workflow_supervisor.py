"""Graph-level workflow supervisor for steering-aware state updates."""

from __future__ import annotations

from typing import Any, Dict

from backend.orchestrator.agents.steering_judge import judge as judge_steering
from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.event_bus import emit_agent_event


async def run_workflow_supervisor(state: JobHunterState) -> Dict[str, Any]:
    """Evaluate unprocessed steering messages and persist the result in graph state."""
    human_messages = state.get("human_messages") or []
    processed = state.get("steering_messages_processed", 0)
    if len(human_messages) <= processed:
        return {}

    latest_message = human_messages[-1]
    recent_events = [
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
    session_snapshot = {
        "session_id": state.get("session_id"),
        "status": state.get("status"),
        "keywords": state.get("keywords", []),
        "locations": state.get("locations", []),
        "current_application": state.get("current_application"),
        "agent_statuses": state.get("agent_statuses", {}),
    }

    result = await judge_steering(
        user_message=latest_message,
        session_snapshot=session_snapshot,
        recent_events=recent_events,
    )

    directives = [directive.model_dump() for directive in result.directives]
    updates: Dict[str, Any] = {
        "steering_messages_processed": len(human_messages),
        "pending_supervisor_response": result.response_message,
        "pending_supervisor_directives": directives,
    }
    for directive in result.directives:
        if directive.action == "set_mode" and directive.mode:
            updates["steering_mode"] = directive.mode
            break

    await emit_agent_event(
        state.get("session_id", ""),
        "status",
        {
            "status": "steering",
            "message": result.response_message,
            "directives": directives,
        },
    )
    return updates
