# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Freelance/Contract Matchmaker API routes."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.gateway.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/freelance", tags=["freelance"])

# In-memory registries
_fl_registry: Dict[str, Dict[str, Any]] = {}
_fl_events: Dict[str, list] = {}
_fl_subscribers: Dict[str, list] = {}


class StartFreelanceRequest(BaseModel):
    resume_text: str
    hourly_rate_min: float = 50.0
    hourly_rate_max: float = 120.0
    platforms: List[str] = Field(default_factory=lambda: ["upwork", "linkedin"])
    project_types: List[str] = Field(default_factory=list)
    availability: str = "part_time"


class FreelanceResponse(BaseModel):
    session_id: str


def _emit_fl(session_id: str, event_type: str, data: Any):
    """Log and broadcast an SSE event."""
    event = {
        "type": event_type,
        "data": data if isinstance(data, dict) else {"message": str(data)},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _fl_events.setdefault(session_id, []).append(event)
    for q in _fl_subscribers.get(session_id, []):
        q.put_nowait(event)


async def _run_freelance_pipeline(session_id: str, graph, config, initial_state):
    """Run the freelance matchmaker graph in the background."""
    try:
        _emit_fl(session_id, "status", {"status": "starting", "message": "Starting freelance gig search..."})
        async for chunk in graph.astream(initial_state, config, stream_mode="values", version="v2"):
            snapshot = chunk["data"]
            status = snapshot.get("status", "")
            if status:
                messages = {
                    "generating_profiles": "Generating your freelance profiles...",
                    "discovering_gigs": "Searching for matching gigs across platforms...",
                    "generating_proposals": "Writing personalized proposals...",
                }
                _emit_fl(session_id, "status", {"status": status, "message": messages.get(status, status)})

            if snapshot.get("profiles") and not _fl_registry[session_id].get("profiles_emitted"):
                _emit_fl(session_id, "profiles_ready", {"profiles": snapshot["profiles"]})
                _fl_registry[session_id]["profiles_emitted"] = True

            if snapshot.get("scored_gigs") and not _fl_registry[session_id].get("gigs_emitted"):
                _emit_fl(session_id, "gigs_found", {
                    "gigs": snapshot["scored_gigs"],
                    "total": len(snapshot["scored_gigs"]),
                })
                _fl_registry[session_id]["gigs_emitted"] = True

            if snapshot.get("proposals") and not _fl_registry[session_id].get("proposals_emitted"):
                _emit_fl(session_id, "proposals_ready", {
                    "proposals": snapshot["proposals"],
                    "total": len(snapshot["proposals"]),
                })
                _fl_registry[session_id]["proposals_emitted"] = True

        _emit_fl(session_id, "done", {"message": "Freelance search complete! Review your proposals."})
        _fl_registry[session_id]["status"] = "completed"
    except Exception as exc:
        logger.exception("Freelance pipeline failed for %s", session_id)
        _emit_fl(session_id, "error", {"message": str(exc)})
        _fl_registry[session_id]["status"] = "failed"


@router.post("", response_model=FreelanceResponse)
async def start_freelance(request: Request, body: StartFreelanceRequest):
    """Start a new freelance gig search."""
    user = get_current_user(request)
    session_id = str(uuid.uuid4())

    _fl_registry[session_id] = {
        "user_id": user["id"],
        "user_email": user["email"],
        "status": "starting",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _fl_events[session_id] = []

    graph = request.app.state.freelance_graph
    config = {"configurable": {"thread_id": f"freelance_{session_id}"}}
    initial_state = {
        "session_id": session_id,
        "user_id": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resume_text": body.resume_text,
        "hourly_rate_min": body.hourly_rate_min,
        "hourly_rate_max": body.hourly_rate_max,
        "platforms": body.platforms,
        "project_types": body.project_types,
        "availability": body.availability,
        "profiles": [],
        "discovered_gigs": [],
        "scored_gigs": [],
        "proposals": {},
        "submitted_proposals": [],
        "total_submitted": 0,
        "total_views": 0,
        "total_shortlisted": 0,
        "status": "starting",
        "errors": [],
    }

    asyncio.create_task(_run_freelance_pipeline(session_id, graph, config, initial_state))
    return FreelanceResponse(session_id=session_id)


@router.get("/{session_id}/stream")
async def stream_freelance(request: Request, session_id: str):
    """SSE stream for a freelance session."""
    if session_id not in _fl_registry:
        raise HTTPException(404, "Freelance session not found")

    queue: asyncio.Queue = asyncio.Queue()
    _fl_subscribers.setdefault(session_id, []).append(queue)

    async def event_generator():
        for event in _fl_events.get(session_id, []):
            yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
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
            if queue in _fl_subscribers.get(session_id, []):
                _fl_subscribers[session_id].remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{session_id}")
async def get_freelance(request: Request, session_id: str):
    """Get current state of a freelance session."""
    if session_id not in _fl_registry:
        raise HTTPException(404, "Freelance session not found")

    meta = _fl_registry[session_id]
    result: Dict[str, Any] = {
        "session_id": session_id,
        "status": meta.get("status", "unknown"),
        "created_at": meta.get("created_at"),
    }

    for event in _fl_events.get(session_id, []):
        if event["type"] == "profiles_ready":
            result["profiles"] = event["data"]["profiles"]
        elif event["type"] == "gigs_found":
            result["gigs"] = event["data"]["gigs"]
        elif event["type"] == "proposals_ready":
            result["proposals"] = event["data"]["proposals"]

    return result
