"""Session lifecycle and SSE streaming routes.

Handles:
  - GET  /api/sessions             -> list all sessions
  - POST /api/sessions             -> start a new pipeline session
  - GET  /api/sessions/{id}        -> retrieve current session state
  - GET  /api/sessions/{id}/stream -> SSE event stream (with replay)
  - POST /api/sessions/{id}/steer  -> inject a steering message
  - POST /api/sessions/{id}/review -> approve/reject the shortlist (HITL)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

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

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

# Session metadata saved at creation time (keywords, status, etc.)
session_registry: Dict[str, dict] = {}

# Append-only event log per session for SSE replay on reconnect.
event_logs: Dict[str, list] = {}

# Per-session list of subscriber queues (one per connected SSE client).
sse_subscribers: Dict[str, List[asyncio.Queue]] = {}


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
    """Log an SSE event and push it to all active subscribers."""
    event = {"type": event_type, "data": data}

    # Append to persistent event log for replay
    if session_id in event_logs:
        event_logs[session_id].append(event)

    # Push to all connected SSE clients
    for queue in sse_subscribers.get(session_id, []):
        await queue.put(event)


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

        await _emit(session_id, "status", {
            "status": "intake",
            "message": "Pipeline started",
            "keywords": request_body.keywords,
            "locations": request_body.locations,
        })

        config = {"configurable": {"thread_id": session_id}}

        async for state_snapshot in graph.astream(initial_state, config=config, stream_mode="values"):
            status = state_snapshot.get("status", "unknown")

            # Update registry status
            if session_id in session_registry:
                session_registry[session_id]["status"] = status

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

            # Track application counts in registry
            if session_id in session_registry:
                session_registry[session_id]["applications_submitted"] = len(
                    state_snapshot.get("applications_submitted", [])
                )
                session_registry[session_id]["applications_failed"] = len(
                    state_snapshot.get("applications_failed", [])
                )

            if status in ("completed", "failed"):
                summary = _serialize(state_snapshot.get("session_summary"))
                await _emit(session_id, "done", {
                    "status": status,
                    "session_summary": summary,
                })
                break

    except Exception as exc:
        logger.exception("Pipeline error for session %s", session_id)
        if session_id in session_registry:
            session_registry[session_id]["status"] = "failed"
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
    """Yield SSE frames: first replay stored events, then stream live.

    Each connected client gets its own subscriber queue so multiple tabs
    or reconnects work independently. Stored events are replayed first,
    then live events stream from the per-subscriber queue.
    """
    # Create a dedicated queue for this subscriber
    subscriber_queue: asyncio.Queue = asyncio.Queue()
    if session_id not in sse_subscribers:
        sse_subscribers[session_id] = []
    sse_subscribers[session_id].append(subscriber_queue)

    try:
        # Phase 1: Replay all previously stored events
        stored = list(event_logs.get(session_id, []))
        for event in stored:
            event_type = event.get("type", "message")
            event_data = json.dumps(event.get("data", {}))
            yield f"event: {event_type}\ndata: {event_data}\n\n"
            # If a terminal event was already stored, stop here
            if event_type == "done":
                return

        # Phase 2: Stream new live events from the subscriber queue
        while True:
            try:
                event = await asyncio.wait_for(subscriber_queue.get(), timeout=25)
                event_type = event.get("type", "message")
                event_data = json.dumps(event.get("data", {}))

                yield f"event: {event_type}\ndata: {event_data}\n\n"

                if event_type == "done":
                    break
            except asyncio.TimeoutError:
                yield f"event: ping\ndata: \"\"\n\n"
    finally:
        # Clean up: remove this subscriber's queue
        subs = sse_subscribers.get(session_id, [])
        if subscriber_queue in subs:
            subs.remove(subscriber_queue)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
async def list_sessions():
    """Return all sessions from the in-memory registry (newest first)."""
    sessions = sorted(
        session_registry.values(),
        key=lambda s: s.get("created_at", ""),
        reverse=True,
    )
    return sessions


@router.post("")
async def start_session(body: StartSessionRequest, request: Request):
    """Create a new pipeline session and begin execution in the background."""
    session_id = str(uuid.uuid4())
    graph = request.app.state.graph

    # Initialize event log and subscriber list
    event_logs[session_id] = []
    sse_subscribers[session_id] = []

    # Register session metadata immediately (before pipeline starts)
    session_registry[session_id] = {
        "session_id": session_id,
        "status": "intake",
        "keywords": body.keywords,
        "locations": body.locations,
        "remote_only": body.remote_only,
        "salary_min": body.salary_min,
        "resume_text_snippet": (body.resume_text or "")[:200],
        "linkedin_url": body.linkedin_url,
        "applications_submitted": 0,
        "applications_failed": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Launch the pipeline as a background coroutine
    asyncio.create_task(_run_pipeline(session_id, body, graph))

    return {"session_id": session_id}


@router.get("/{session_id}")
async def get_session(session_id: str, request: Request):
    """Return session state from checkpointer, falling back to registry."""
    checkpointer = request.app.state.checkpointer
    config = {"configurable": {"thread_id": session_id}}

    try:
        state = await checkpointer.aget(config)
    except Exception:
        state = None

    if state is not None:
        return _serialize(state)

    # Fall back to the session registry (keywords, status, etc.)
    meta = session_registry.get(session_id)
    if meta is not None:
        return meta

    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/{session_id}/stream")
async def stream_session(session_id: str):
    """SSE stream for real-time pipeline updates (with replay on reconnect)."""
    if session_id not in session_registry:
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
