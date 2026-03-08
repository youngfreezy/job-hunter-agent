"""Career Pivot Advisor API routes."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.gateway.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/career-pivot", tags=["career-pivot"])

# In-memory registries (same pattern as sessions.py)
_pivot_registry: Dict[str, Dict[str, Any]] = {}
_pivot_events: Dict[str, list] = {}
_pivot_subscribers: Dict[str, list] = {}


class StartPivotRequest(BaseModel):
    resume_text: str
    location: Optional[str] = "Remote"


class PivotResponse(BaseModel):
    session_id: str


def _emit_pivot(session_id: str, event_type: str, data: Any):
    """Log and broadcast an SSE event for a pivot session."""
    import json
    event = {
        "type": event_type,
        "data": data if isinstance(data, dict) else {"message": str(data)},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _pivot_events.setdefault(session_id, []).append(event)
    for q in _pivot_subscribers.get(session_id, []):
        q.put_nowait(event)


async def _run_pivot_pipeline(session_id: str, graph, config, initial_state):
    """Run the career pivot graph in the background."""
    try:
        _emit_pivot(session_id, "status", {"status": "parsing_skills", "message": "Analyzing your resume..."})
        async for snapshot in graph.astream(initial_state, config, stream_mode="values"):
            status = snapshot.get("status", "")
            if status:
                messages = {
                    "parsing_skills": "Extracting skills from your resume...",
                    "assessing_risk": "Assessing AI automation risk for your role...",
                    "mapping_roles": "Finding adjacent roles you're qualified for...",
                    "completed": "Your pivot report is ready!",
                }
                _emit_pivot(session_id, "status", {"status": status, "message": messages.get(status, status)})

            # Emit results as they become available
            if snapshot.get("automation_risk_score") is not None and not _pivot_registry[session_id].get("risk_emitted"):
                _emit_pivot(session_id, "risk_assessment", {
                    "automation_risk_score": snapshot["automation_risk_score"],
                    "task_breakdown": snapshot.get("task_breakdown", []),
                    "parsed_role": snapshot.get("parsed_role", ""),
                    "parsed_skills": snapshot.get("parsed_skills", []),
                    "years_experience": snapshot.get("years_experience"),
                    "industry": snapshot.get("industry"),
                })
                _pivot_registry[session_id]["risk_emitted"] = True

            if snapshot.get("recommended_pivots") and not _pivot_registry[session_id].get("pivots_emitted"):
                _emit_pivot(session_id, "pivot_roles", {
                    "recommended_pivots": snapshot["recommended_pivots"],
                })
                _pivot_registry[session_id]["pivots_emitted"] = True

        _emit_pivot(session_id, "done", {"message": "Career pivot analysis complete"})
        _pivot_registry[session_id]["status"] = "completed"
    except Exception as exc:
        logger.exception("Career pivot pipeline failed for %s", session_id)
        _emit_pivot(session_id, "error", {"message": str(exc)})
        _pivot_registry[session_id]["status"] = "failed"


@router.post("", response_model=PivotResponse)
async def start_pivot(request: Request, body: StartPivotRequest):
    """Start a new career pivot analysis."""
    user = get_current_user(request)
    session_id = str(uuid.uuid4())

    _pivot_registry[session_id] = {
        "user_id": user["id"],
        "user_email": user["email"],
        "status": "starting",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _pivot_events[session_id] = []

    graph = request.app.state.career_pivot_graph
    config = {"configurable": {"thread_id": f"pivot_{session_id}"}}
    initial_state = {
        "session_id": session_id,
        "user_id": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resume_text": body.resume_text,
        "location": body.location,
        "status": "starting",
        "errors": [],
        "parsed_skills": [],
        "task_breakdown": [],
        "recommended_pivots": [],
        "report_generated": False,
    }

    asyncio.create_task(_run_pivot_pipeline(session_id, graph, config, initial_state))
    return PivotResponse(session_id=session_id)


@router.get("/{session_id}/stream")
async def stream_pivot(request: Request, session_id: str):
    """SSE stream for a career pivot session."""
    if session_id not in _pivot_registry:
        raise HTTPException(404, "Pivot session not found")

    queue: asyncio.Queue = asyncio.Queue()
    _pivot_subscribers.setdefault(session_id, []).append(queue)

    async def event_generator():
        import json
        # Replay existing events
        for event in _pivot_events.get(session_id, []):
            yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"

        # Stream new events
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
                    if event["type"] in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    yield f"event: ping\ndata: {json.dumps({'ping': True})}\n\n"
        finally:
            if queue in _pivot_subscribers.get(session_id, []):
                _pivot_subscribers[session_id].remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{session_id}")
async def get_pivot(request: Request, session_id: str):
    """Get current state of a career pivot session."""
    if session_id not in _pivot_registry:
        raise HTTPException(404, "Pivot session not found")

    meta = _pivot_registry[session_id]
    # Collect latest data from events
    result: Dict[str, Any] = {
        "session_id": session_id,
        "status": meta.get("status", "unknown"),
        "created_at": meta.get("created_at"),
    }

    for event in _pivot_events.get(session_id, []):
        if event["type"] == "risk_assessment":
            result["risk_assessment"] = event["data"]
        elif event["type"] == "pivot_roles":
            result["pivot_roles"] = event["data"]

    return result
