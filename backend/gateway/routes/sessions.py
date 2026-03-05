"""Session lifecycle and SSE streaming routes.

Handles:
  - GET  /api/sessions                  -> list all sessions
  - POST /api/sessions                  -> start a new pipeline session
  - GET  /api/sessions/{id}             -> retrieve current session state
  - GET  /api/sessions/{id}/stream      -> SSE event stream (with replay)
  - POST /api/sessions/{id}/steer       -> inject a steering message
  - POST /api/sessions/{id}/coach-review -> approve/edit coached resume (HITL)
  - POST /api/sessions/{id}/review      -> approve/reject the shortlist (HITL)
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

from langgraph.types import Command

from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.config import MAX_APPLICATION_JOBS
from backend.shared.event_bus import register_emitter, unregister_emitter
from backend.shared.models.schemas import (
    CoachReviewRequest,
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


STATUS_MESSAGES = {
    "intake": "Processing your input...",
    "coaching": "Analyzing and coaching your resume (this may take 30-60 seconds)...",
    "discovering": "Scanning job boards for matches...",
    "scoring": "Scoring and ranking discovered jobs...",
    "tailoring": "Tailoring resumes for top matches...",
    "awaiting_review": "Ready for your review",
    "applying": "Submitting applications...",
    "verifying": "Verifying submitted applications...",
    "reporting": "Generating session report...",
    "completed": "Pipeline complete",
    "failed": "Pipeline encountered an error",
}


async def _stream_graph(
    session_id: str,
    graph: Any,
    config: dict,
    input_state: Any,
) -> str | None:
    """Stream a graph run and emit SSE events for each state snapshot.

    Returns the interrupt stage name (e.g. "coach_review") if the graph
    paused at an interrupt, or None if it ran to completion/failure.
    """
    last_status = "unknown"

    async for state_snapshot in graph.astream(input_state, config=config, stream_mode="values"):
        # Yield to the event loop so health checks / SSE / API calls aren't starved
        await asyncio.sleep(0)

        status = state_snapshot.get("status", "unknown")
        last_status = status

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
            all_scored = state_snapshot.get("scored_jobs", [])
            top_scored = sorted(all_scored, key=lambda sj: sj.score, reverse=True)[:MAX_APPLICATION_JOBS]
            shortlist = [_serialize(sj) for sj in top_scored]
            await _emit(session_id, "hitl", {
                "status": "awaiting_review",
                "shortlist": shortlist,
                "message": "Please review and approve jobs to apply to.",
            })

        # Generic status update for every snapshot
        await _emit(session_id, "status", {
            "status": status,
            "message": STATUS_MESSAGES.get(status, status),
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
            return None  # Terminal — no interrupt

    # Stream ended without terminal status — check for interrupt
    if last_status not in ("completed", "failed"):
        try:
            graph_state = await graph.aget_state(config)
            # LangGraph stores pending tasks/interrupts in the state
            next_nodes = getattr(graph_state, "next", ()) or ()
            if next_nodes:
                logger.info(
                    "Pipeline paused at interrupt for session %s, next=%s",
                    session_id,
                    next_nodes,
                )
                # Determine which interrupt we're at
                if "coach_review" in next_nodes:
                    return "coach_review"
                elif "shortlist_review" in next_nodes:
                    return "shortlist_review"
                else:
                    return str(next_nodes[0]) if next_nodes else None
        except Exception:
            logger.exception("Failed to check graph state for session %s", session_id)

    return None


async def _handle_shortlist_interrupt(session_id: str, graph: Any, config: dict) -> None:
    """Emit the shortlist_review SSE event when the pipeline pauses for review."""
    if session_id in session_registry:
        session_registry[session_id]["status"] = "awaiting_review"
    try:
        graph_state = await graph.aget_state(config)
        channel_values = graph_state.values if hasattr(graph_state, "values") else {}
        all_scored = channel_values.get("scored_jobs", [])
        top_scored = sorted(all_scored, key=lambda sj: sj.score, reverse=True)[:MAX_APPLICATION_JOBS]
        tailored_resumes = channel_values.get("tailored_resumes", {})
        await _emit(session_id, "shortlist_review", {
            "status": "awaiting_review",
            "scored_jobs": _serialize(top_scored),
            "tailored_resumes": _serialize(tailored_resumes),
            "message": "Review the shortlist and approve jobs to apply to.",
        })
    except Exception:
        logger.exception("Failed to emit shortlist review event for session %s", session_id)


async def _run_pipeline(
    session_id: str,
    request_body: StartSessionRequest,
    graph: Any,
) -> None:
    """Execute the LangGraph pipeline and emit SSE events as agents complete.

    Runs as a background task so the POST /api/sessions response returns
    immediately with the session_id. Handles interrupt detection for HITL
    gates (coach review, shortlist review).
    """
    # Register the emit callback so agents can send SSE events directly
    register_emitter(session_id, _emit)

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

        interrupt_stage = await _stream_graph(session_id, graph, config, initial_state)

        if interrupt_stage == "coach_review":
            # Pipeline is paused at coach review — emit the review event
            try:
                graph_state = await graph.aget_state(config)
                channel_values = graph_state.values if hasattr(graph_state, "values") else {}
                coach_output = channel_values.get("coach_output")

                if session_id in session_registry:
                    session_registry[session_id]["status"] = "awaiting_coach_review"

                await _emit(session_id, "coach_review", {
                    "status": "awaiting_coach_review",
                    "coach_output": _serialize(coach_output) if coach_output else None,
                    "coached_resume": channel_values.get("coached_resume", ""),
                    "message": "Please review your coached resume. Approve to continue to job discovery.",
                })
            except Exception:
                logger.exception("Failed to emit coach review event for session %s", session_id)

            # Do NOT unregister emitter or send "done" — pipeline will resume
            return

        if interrupt_stage == "shortlist_review":
            await _handle_shortlist_interrupt(session_id, graph, config)
            return

    except Exception as exc:
        logger.exception("Pipeline error for session %s", session_id)
        if session_id in session_registry:
            session_registry[session_id]["status"] = "failed"
        await _emit(session_id, "error", {
            "message": str(exc),
            "session_id": session_id,
        })
        await _emit(session_id, "done", {
            "status": "failed",
            "error": str(exc),
        })
        unregister_emitter(session_id)


async def _resume_pipeline(
    session_id: str,
    graph: Any,
    resume_value: Any = None,
    checkpoint_id: str | None = None,
) -> None:
    """Resume the pipeline after an interrupt (coach review or shortlist review).

    Uses Command(resume=value) to provide the human input back to the
    interrupt() call that paused the graph.

    If checkpoint_id is provided, resumes from that specific checkpoint
    instead of the latest one (used for rewind).
    """
    # Ensure emitter is registered for this session
    register_emitter(session_id, _emit)

    config: dict = {"configurable": {"thread_id": session_id}}
    if checkpoint_id:
        config["configurable"]["checkpoint_id"] = checkpoint_id

    # Build the resume input — Command(resume=...) feeds the value back
    # to the interrupt() call that paused execution.
    resume_input = Command(resume=resume_value) if resume_value is not None else None

    try:
        interrupt_stage = await _stream_graph(session_id, graph, config, resume_input)

        if interrupt_stage == "shortlist_review":
            await _handle_shortlist_interrupt(session_id, graph, config)
            return

        # If another interrupt, handle it (could be extended for more HITL gates)
        if interrupt_stage:
            logger.info("Pipeline paused at %s for session %s", interrupt_stage, session_id)
            return

    except Exception as exc:
        logger.exception("Pipeline resume error for session %s", session_id)
        if session_id in session_registry:
            session_registry[session_id]["status"] = "failed"
        await _emit(session_id, "error", {
            "message": str(exc),
            "session_id": session_id,
        })
        await _emit(session_id, "done", {
            "status": "failed",
            "error": str(exc),
        })
    finally:
        # Only unregister if pipeline is truly done (no more interrupts expected)
        # The finally block runs after _stream_graph returns None (terminal)
        pass


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


# ---------------------------------------------------------------------------
# Test endpoint: isolated application with screenshot streaming
# ---------------------------------------------------------------------------

from pydantic import BaseModel as _BaseModel


class TestApplyRequest(_BaseModel):
    job_url: str
    job_title: str = "Software Engineer"
    company: str = "Unknown"
    resume_text: str = ""


@router.post("/test-apply")
async def test_apply_endpoint(body: TestApplyRequest, request: Request):
    """Run a single job application in isolation with screenshot streaming.

    Returns a session_id. Open http://localhost:3000/session/{session_id}
    and switch to the Screenshot Feed tab to watch live.
    """
    session_id = f"test-{uuid.uuid4().hex[:8]}"

    event_logs[session_id] = []
    sse_subscribers[session_id] = []
    session_registry[session_id] = {
        "session_id": session_id,
        "status": "applying",
        "keywords": [body.job_title],
        "locations": [],
        "remote_only": False,
        "salary_min": None,
        "resume_text_snippet": body.resume_text[:200],
        "linkedin_url": None,
        "applications_submitted": 0,
        "applications_failed": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    register_emitter(session_id, _emit)

    await _emit(session_id, "status", {
        "status": "applying",
        "message": f"Testing application to {body.job_url}",
    })

    asyncio.create_task(_test_apply_single(
        session_id=session_id,
        job_url=body.job_url,
        job_title=body.job_title,
        company=body.company,
        resume_text=body.resume_text,
    ))

    return {
        "session_id": session_id,
        "message": f"Test apply started. Watch at /session/{session_id} (Screenshot Feed tab)",
    }


async def _test_apply_single(
    session_id: str,
    job_url: str,
    job_title: str,
    company: str,
    resume_text: str,
) -> None:
    """Background task: run a single application with live SSE + screenshot streaming."""
    from backend.orchestrator.agents.application import _apply_with_playwright
    from backend.shared.models.schemas import JobListing, JobBoard

    dummy_job = JobListing(
        id=f"test-{uuid.uuid4().hex[:6]}",
        title=job_title,
        company=company,
        location="Remote",
        url=job_url,
        board=JobBoard.INDEED,
    )

    state = {
        "session_id": session_id,
        "resume_text": resume_text or "No resume provided",
        "coached_resume": resume_text or "",
        "cover_letter_template": "",
        "resume_file_path": None,
        "discovered_jobs": [dummy_job],
        "scored_jobs": [],
    }

    try:
        await _emit(session_id, "status", {
            "status": "applying",
            "message": f"Applying to {job_title} at {company}...",
        })

        result = await _apply_with_playwright(
            job_id=dummy_job.id,
            job=dummy_job,
            state=state,
            session_id=session_id,
        )

        final_status = "completed" if result.status.value == "submitted" else "failed"
        await _emit(session_id, "status", {
            "status": final_status,
            "message": f"Result: {result.status.value} — {result.error_message or 'OK'}",
        })
        await _emit(session_id, "done", {
            "status": final_status,
            "message": f"Application {result.status.value}",
            "error": result.error_message,
            "duration_seconds": result.duration_seconds,
        })

    except Exception as exc:
        logger.exception("Test apply failed for %s", session_id)
        await _emit(session_id, "error", {"message": str(exc)})
        await _emit(session_id, "done", {"status": "failed", "error": str(exc)})
    finally:
        if session_id in session_registry:
            session_registry[session_id]["status"] = "completed"
        unregister_emitter(session_id)


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
        # Extract channel_values from the checkpoint (the actual state dict)
        checkpoint = state
        if hasattr(state, "checkpoint"):
            checkpoint = state.checkpoint
        if isinstance(checkpoint, dict) and "channel_values" in checkpoint:
            cv = checkpoint["channel_values"]
        else:
            cv = checkpoint

        # Strip heavy fields that the frontend gets via SSE instead.
        # This prevents serializing megabytes of tailored resumes on every poll.
        HEAVY_KEYS = {
            "tailored_resumes", "resume_scores", "messages",
            "resume_text", "coached_resume", "cover_letter_template",
        }
        if isinstance(cv, dict):
            cv_light = {k: v for k, v in cv.items() if k not in HEAVY_KEYS}
            if "scored_jobs" in cv_light and cv_light["scored_jobs"]:
                all_scored = cv_light["scored_jobs"]
                cv_light["scored_jobs"] = sorted(
                    all_scored, key=lambda sj: sj.score if hasattr(sj, "score") else sj.get("score", 0), reverse=True
                )[:MAX_APPLICATION_JOBS]
        else:
            cv_light = cv

        result = _serialize(cv_light)

        # The checkpointer's status may not reflect HITL pauses (e.g. it shows
        # "discovering" when the graph is actually paused at coach_review).
        # Overlay the registry status which is managed by _run_pipeline.
        meta = session_registry.get(session_id)
        if meta and isinstance(result, dict):
            registry_status = meta.get("status")
            if registry_status:
                result["status"] = registry_status
        return result

    # Fall back to the session registry (keywords, status, etc.)
    meta = session_registry.get(session_id)
    if meta is not None:
        return meta

    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/{session_id}/checkpoints")
async def list_checkpoints(session_id: str, request: Request):
    """List all checkpoints for a session (for rewind UI)."""
    checkpointer = request.app.state.checkpointer
    config = {"configurable": {"thread_id": session_id}}

    checkpoints = []
    try:
        async for cp in checkpointer.alist(config):
            cv = {}
            if hasattr(cp, "checkpoint") and isinstance(cp.checkpoint, dict):
                cv = cp.checkpoint.get("channel_values", {})
            elif isinstance(cp, dict):
                cv = cp.get("channel_values", {})

            cp_id = ""
            if hasattr(cp, "config"):
                cp_id = cp.config.get("configurable", {}).get("checkpoint_id", "")

            status = cv.get("status", "unknown")
            apps_submitted = len(cv.get("applications_submitted", []))
            apps_failed = len(cv.get("applications_failed", []))
            app_queue = len(cv.get("application_queue", []))

            checkpoints.append({
                "checkpoint_id": cp_id,
                "status": status,
                "applications_submitted": apps_submitted,
                "applications_failed": apps_failed,
                "application_queue": app_queue,
            })
    except Exception:
        logger.exception("Failed to list checkpoints for session %s", session_id)

    return {"checkpoints": checkpoints}


@router.get("/{session_id}/stream")
async def stream_session(session_id: str, request: Request):
    """SSE stream for real-time pipeline updates (with replay on reconnect)."""
    if session_id not in session_registry:
        # Try to recover from checkpointer (e.g. after backend restart)
        checkpointer = request.app.state.checkpointer
        config = {"configurable": {"thread_id": session_id}}
        try:
            state = await checkpointer.aget(config)
        except Exception:
            state = None
        if state is None:
            raise HTTPException(status_code=404, detail="Session not found or stream expired")
        # Re-register the session from checkpoint data
        cv = {}
        if hasattr(state, "checkpoint"):
            cv = state.checkpoint.get("channel_values", {}) if isinstance(state.checkpoint, dict) else {}
        elif isinstance(state, dict):
            cv = state.get("channel_values", state)
        session_registry[session_id] = {
            "session_id": session_id,
            "status": cv.get("status", "unknown"),
            "keywords": cv.get("keywords", []),
            "locations": cv.get("locations", []),
            "remote_only": cv.get("remote_only", False),
            "salary_min": cv.get("salary_min"),
            "resume_text_snippet": (cv.get("resume_text", "") or "")[:200],
            "linkedin_url": cv.get("linkedin_url"),
            "applications_submitted": len(cv.get("applications_submitted", [])),
            "applications_failed": len(cv.get("applications_failed", [])),
            "created_at": cv.get("created_at", ""),
        }
        logger.info("Recovered session %s from checkpointer (status=%s)", session_id, cv.get("status"))

    # Ensure event log and subscriber list exist
    if session_id not in event_logs:
        event_logs[session_id] = []
    if session_id not in sse_subscribers:
        sse_subscribers[session_id] = []

    return StreamingResponse(
        _event_generator(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/{session_id}/coach-review")
async def submit_coach_review(session_id: str, body: CoachReviewRequest, request: Request):
    """Resume the pipeline after the user reviews the coached resume."""
    graph = request.app.state.graph

    # Build the human input that coach_review_gate's interrupt() will receive
    human_input: Dict[str, Any] = {"approved": body.approved}
    if body.edited_resume:
        human_input["edited_resume"] = body.edited_resume
    if body.feedback:
        human_input["feedback"] = body.feedback

    if session_id in session_registry:
        session_registry[session_id]["status"] = "discovering"

    await _emit(session_id, "status", {
        "status": "discovering",
        "message": "Resume approved! Starting job discovery...",
    })

    # Resume the pipeline with Command(resume=human_input)
    asyncio.create_task(_resume_pipeline(session_id, graph, resume_value=human_input))

    return {"status": "ok", "message": "Coach review submitted, pipeline resuming"}


@router.post("/{session_id}/steer")
async def steer_session(session_id: str, body: SteerRequest, request: Request):
    """Inject a steering message into the running session."""
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": session_id}}

    try:
        state_update: Dict[str, Any] = {"human_messages": [body.message]}
        if body.mode:
            state_update["steering_mode"] = body.mode.value
        await graph.aupdate_state(config, state_update)
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

    # Build the human input that shortlist_review_gate's interrupt() will receive
    human_input: Dict[str, Any] = {
        "approved_job_ids": body.approved_job_ids,
        "feedback": body.feedback or "",
    }

    if session_id in session_registry:
        session_registry[session_id]["status"] = "applying"

    await _emit(session_id, "status", {
        "status": "applying",
        "message": f"Approved {len(body.approved_job_ids)} jobs for application",
        "approved_count": len(body.approved_job_ids),
    })

    # Resume the pipeline with Command(resume=human_input)
    asyncio.create_task(_resume_pipeline(session_id, graph, resume_value=human_input))

    return {
        "status": "ok",
        "approved_count": len(body.approved_job_ids),
    }


@router.post("/{session_id}/resume-intervention")
async def resume_intervention(session_id: str):
    """Signal the application agent to continue after user intervention."""
    try:
        import redis.asyncio as aioredis
        from backend.shared.config import get_settings
        settings = get_settings()
        redis_client = aioredis.from_url(settings.REDIS_URL)
        await redis_client.set(f"intervention:resume:{session_id}", "1", ex=600)
        await redis_client.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to signal resume: {exc}")

    await _emit(session_id, "status", {
        "status": "applying",
        "message": "User intervention complete — agent resuming...",
    })

    return {"status": "ok", "message": "Intervention resume signal sent"}


class SubmitDecisionRequest(_BaseModel):
    decision: str = "submit"  # "submit" or "skip"


@router.post("/{session_id}/submit-decision")
async def submit_decision(session_id: str, body: SubmitDecisionRequest):
    """Approve or skip a pending application submission."""
    if body.decision not in ("submit", "skip"):
        raise HTTPException(status_code=400, detail="decision must be 'submit' or 'skip'")

    try:
        import redis.asyncio as aioredis
        from backend.shared.config import get_settings
        settings = get_settings()
        redis_client = aioredis.from_url(settings.REDIS_URL)
        await redis_client.set(f"submit:approve:{session_id}", body.decision, ex=600)
        await redis_client.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to send decision: {exc}")

    action = "Submitting" if body.decision == "submit" else "Skipping"
    await _emit(session_id, "status", {
        "status": "applying",
        "message": f"{action} application...",
    })

    return {"status": "ok", "decision": body.decision}


class RewindRequest(_BaseModel):
    checkpoint_id: str
    approved_job_ids: list[str] | None = None


@router.post("/{session_id}/rewind")
async def rewind_session(session_id: str, body: RewindRequest, request: Request):
    """Rewind a session to a specific checkpoint and resume the pipeline.

    This loads the graph state from the given checkpoint_id (which must be
    at an interrupt) and resumes execution from there.
    """
    graph = request.app.state.graph
    config = {
        "configurable": {
            "thread_id": session_id,
            "checkpoint_id": body.checkpoint_id,
        }
    }

    # Verify the checkpoint exists and is at an interrupt
    try:
        graph_state = await graph.aget_state(config)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Checkpoint not found: {exc}")

    next_nodes = getattr(graph_state, "next", ()) or ()
    if not next_nodes:
        raise HTTPException(
            status_code=400,
            detail="Checkpoint is not at an interrupt — cannot resume from here",
        )

    # Determine which interrupt we're at and build the resume value
    if "shortlist_review" in next_nodes:
        channel_values = graph_state.values if hasattr(graph_state, "values") else {}
        if body.approved_job_ids:
            approved = body.approved_job_ids
        else:
            approved = channel_values.get("application_queue", [])

        resume_value = {
            "approved_job_ids": approved,
            "feedback": "Rewind: resuming application phase",
        }
    elif "coach_review" in next_nodes:
        resume_value = {"approved": True}
    else:
        resume_value = {}

    # Clear old event log and start fresh for the resumed phase
    event_logs[session_id] = []
    sse_subscribers.setdefault(session_id, [])

    # Update registry
    if session_id not in session_registry:
        session_registry[session_id] = {
            "session_id": session_id,
            "status": "applying",
            "keywords": [],
            "locations": [],
            "remote_only": False,
            "salary_min": None,
            "resume_text_snippet": "",
            "linkedin_url": None,
            "applications_submitted": 0,
            "applications_failed": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    session_registry[session_id]["status"] = "applying"

    await _emit(session_id, "status", {
        "status": "applying",
        "message": f"Rewound to checkpoint — resuming with {len(resume_value.get('approved_job_ids', []))} jobs",
    })

    # Resume the pipeline from the rewound checkpoint
    asyncio.create_task(_resume_pipeline(
        session_id, graph, resume_value=resume_value, checkpoint_id=body.checkpoint_id
    ))

    return {
        "status": "ok",
        "checkpoint_id": body.checkpoint_id,
        "next_nodes": list(next_nodes),
        "message": f"Resuming from {next_nodes}",
    }
