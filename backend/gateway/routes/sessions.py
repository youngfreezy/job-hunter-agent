"""Session lifecycle and SSE streaming routes.

Handles:
  - POST /api/sessions          -> start a new pipeline session
  - GET  /api/sessions/{id}     -> retrieve current session state
  - GET  /api/sessions/{id}/stream -> SSE event stream
  - POST /api/sessions/{id}/steer  -> inject a steering message
  - POST /api/sessions/{id}/review -> approve/reject the shortlist (HITL)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.models.schemas import (
    ReviewRequest,
    SSEEvent,
    StartSessionRequest,
    SteerRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# In-memory SSE queues keyed by session_id.
# Each queue carries dicts with {"type": str, "data": dict}.
sse_queues: Dict[str, asyncio.Queue] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize(obj: Any) -> Any:
    """Make an object JSON-safe (handles Pydantic models, datetimes, etc.)."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    return obj


async def _emit(session_id: str, event_type: str, data: dict) -> None:
    """Push an SSE event into the queue for *session_id*."""
    queue = sse_queues.get(session_id)
    if queue is not None:
        await queue.put({"type": event_type, "data": data})


async def _run_pipeline(
    session_id: str,
    request_body: StartSessionRequest,
    graph: Any,
) -> None:
    """Execute the LangGraph pipeline and emit SSE events as agents complete.

    Runs as a background task so the POST /api/sessions response returns
    immediately with the session_id.
    """
    try:
        # Build the initial state
        initial_state: Dict[str, Any] = {
            "session_id": session_id,
            "user_id": "test-user",  # TODO: resolve from auth
            "created_at": datetime.now(timezone.utc).isoformat(),
            "keywords": request_body.keywords,
            "locations": request_body.locations,
            "remote_only": request_body.remote_only,
            "salary_min": request_body.salary_min,
            "resume_text": request_body.resume_text or "",
            "resume_file_path": None,
            "linkedin_url": request_body.linkedin_url,
            "preferences": request_body.preferences,
            "status": "intake",
            "discovered_jobs": [],
            "scored_jobs": [],
            "tailored_resumes": {},
            "resume_scores": {},
            "application_queue": [],
            "current_application": None,
            "applications_submitted": [],
            "applications_failed": [],
            "applications_skipped": [],
            "agent_statuses": {},
            "human_messages": [],
            "steering_mode": "status",
            "messages": [],
            "errors": [],
            "consecutive_failures": 0,
            "applications_used": 0,
        }

        await _emit(session_id, "status", {"status": "intake", "message": "Pipeline started"})

        config = {"configurable": {"thread_id": session_id}}

        async for state_snapshot in graph.astream(initial_state, config=config, stream_mode="values"):
            status = state_snapshot.get("status", "unknown")

            # Emit agent-specific events based on current pipeline status
            if status == "coaching" and state_snapshot.get("coach_output"):
                await _emit(session_id, "coaching", {
                    "status": "coaching",
                    "coach_output": _serialize(state_snapshot["coach_output"]),
                })

            if status == "discovering":
                await _emit(session_id, "discovery", {
                    "status": "discovering",
                    "jobs_found": len(state_snapshot.get("discovered_jobs", [])),
                })

            if status == "scoring" and state_snapshot.get("scored_jobs"):
                await _emit(session_id, "scoring", {
                    "status": "scoring",
                    "scored_count": len(state_snapshot["scored_jobs"]),
                    "top_score": max(
                        (j.score for j in state_snapshot["scored_jobs"]),
                        default=0,
                    ),
                })

            if status == "awaiting_review":
                shortlist = [
                    _serialize(sj)
                    for sj in state_snapshot.get("scored_jobs", [])
                ]
                await _emit(session_id, "hitl", {
                    "status": "awaiting_review",
                    "shortlist": shortlist,
                    "message": "Please review and approve jobs to apply to.",
                })

            # Generic status update for every snapshot
            await _emit(session_id, "status", {
                "status": status,
                "agent_statuses": state_snapshot.get("agent_statuses", {}),
            })

            # Agent completion signals
            agent_statuses = state_snapshot.get("agent_statuses", {})
            for agent_name, agent_status in agent_statuses.items():
                if agent_status == "done":
                    await _emit(session_id, "agent_complete", {
                        "agent": agent_name,
                        "status": "done",
                    })

            if status in ("completed", "failed"):
                summary = _serialize(state_snapshot.get("session_summary"))
                await _emit(session_id, "done", {
                    "status": status,
                    "session_summary": summary,
                })
                break

    except Exception as exc:
        logger.exception("Pipeline error for session %s", session_id)
        await _emit(session_id, "error", {
            "message": str(exc),
            "session_id": session_id,
        })
        # Always send a terminal event so the SSE stream closes cleanly
        await _emit(session_id, "done", {
            "status": "failed",
            "error": str(exc),
        })


# ---------------------------------------------------------------------------
# SSE event generator
# ---------------------------------------------------------------------------

async def _event_generator(session_id: str):
    """Yield SSE frames from the session's queue.

    Sends a keepalive ping every 25 seconds if no events arrive.
    """
    queue = sse_queues.get(session_id)
    if queue is None:
        yield f"event: error\ndata: {json.dumps({'message': 'Unknown session'})}\n\n"
        return

    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=25)
            event_type = event.get("type", "message")
            event_data = json.dumps(event.get("data", {}))

            yield f"event: {event_type}\ndata: {event_data}\n\n"

            if event_type == "done":
                break
        except asyncio.TimeoutError:
            yield f"event: ping\ndata: \"\"\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("")
async def start_session(body: StartSessionRequest, request: Request):
    """Create a new pipeline session and begin execution in the background."""
    session_id = str(uuid.uuid4())
    graph = request.app.state.graph

    # Create the SSE queue for this session
    sse_queues[session_id] = asyncio.Queue()

    # Launch the pipeline as a background coroutine
    asyncio.create_task(_run_pipeline(session_id, body, graph))

    return {"session_id": session_id}


@router.get("/{session_id}")
async def get_session(session_id: str, request: Request):
    """Return the current session state from the checkpointer."""
    checkpointer = request.app.state.checkpointer
    config = {"configurable": {"thread_id": session_id}}

    try:
        state = await checkpointer.aget(config)
    except Exception:
        state = None

    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return _serialize(state)


@router.get("/{session_id}/stream")
async def stream_session(session_id: str):
    """SSE stream for real-time pipeline updates."""
    if session_id not in sse_queues:
        raise HTTPException(status_code=404, detail="Session not found or stream expired")

    return StreamingResponse(
        _event_generator(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/{session_id}/steer")
async def steer_session(session_id: str, body: SteerRequest, request: Request):
    """Inject a steering message into the running session."""
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": session_id}}

    try:
        await graph.aupdate_state(
            config,
            {"human_messages": [body.message]},
        )
    except Exception as exc:
        logger.exception("Failed to steer session %s", session_id)
        raise HTTPException(status_code=500, detail=str(exc))

    await _emit(session_id, "status", {
        "status": "steering",
        "message": f"Steering message received: {body.message}",
    })

    return {"status": "ok", "message": "Steering message injected"}


@router.post("/{session_id}/review")
async def review_shortlist(session_id: str, body: ReviewRequest, request: Request):
    """Resume the pipeline after HITL shortlist review."""
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": session_id}}

    try:
        # Update state with approved jobs and resume the graph
        await graph.aupdate_state(
            config,
            {
                "application_queue": body.approved_job_ids,
                "status": "applying",
                "human_messages": [body.feedback] if body.feedback else [],
            },
        )
    except Exception as exc:
        logger.exception("Failed to submit review for session %s", session_id)
        raise HTTPException(status_code=500, detail=str(exc))

    await _emit(session_id, "status", {
        "status": "applying",
        "message": f"Approved {len(body.approved_job_ids)} jobs for application",
        "approved_count": len(body.approved_job_ids),
    })

    return {
        "status": "ok",
        "approved_count": len(body.approved_job_ids),
    }
