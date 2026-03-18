# Copyright (c) 2026 V2 Software LLC. All rights reserved.

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
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from backend.orchestrator.pipeline.state import JobHunterState
from backend.orchestrator.agents.coach_chat import revise_coach_output
from backend.orchestrator.agents.workflow_supervisor import preview_steering_message
from backend.shared.config import MAX_APPLICATION_JOBS
from backend.shared.event_bus import register_emitter, unregister_emitter
from backend.shared.session_store import (
    upsert_session,
    update_session_status,
    update_session_counts,
    get_sessions_for_user,
)
from backend.shared.models.schemas import (
    CoachReviewRequest,
    CoachOutput,
    CoachChatRequest,
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

# Keep strong references to fire-and-forget background tasks so they don't get
# garbage-collected while still running.
_background_tasks: set[asyncio.Task[Any]] = set()


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


def _set_session_status(session_id: str, status: str) -> None:
    """Update session status in both in-memory registry and Postgres."""
    if session_id in session_registry:
        session_registry[session_id]["status"] = status
    update_session_status(session_id, status)


def _set_session_counts(
    session_id: str, submitted: int, failed: int
) -> None:
    """Update application counts in both in-memory registry and Postgres."""
    if session_id in session_registry:
        session_registry[session_id]["applications_submitted"] = submitted
        session_registry[session_id]["applications_failed"] = failed
    update_session_counts(session_id, submitted, failed)


def _spawn_background(coro: Any) -> asyncio.Task[Any]:
    """Create and retain a background task until completion."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def _release_task_slot(session_id: str) -> None:
    """Release the task queue concurrency slot for a completed/failed session."""
    try:
        from backend.shared.task_queue import mark_complete
        await mark_complete(session_id)
    except Exception:
        logger.debug("Failed to release task queue slot for %s", session_id, exc_info=True)


async def _send_completion_notifications(session_id: str) -> None:
    """Send session-complete email and/or SMS notifications (best-effort)."""
    try:
        from backend.shared.email_notifications import send_session_complete_email
        from backend.shared.sms import send_session_complete_sms
        from backend.shared.billing_store import get_user_by_id
        from backend.shared.application_store import get_results_for_session

        meta = session_registry.get(session_id, {})
        user_id = meta.get("user_id")
        if not user_id:
            return

        # Compute actual stats from DB
        results = get_results_for_session(session_id)
        total_applied = sum(1 for r in results if r["status"] == "submitted")
        total_failed = sum(1 for r in results if r["status"] == "failed")
        total_skipped = sum(1 for r in results if r["status"] == "skipped")
        top_companies = list(
            {r["job"]["company"] for r in results if r["status"] == "submitted" and r["job"].get("company")}
        )[:5]

        # Compute duration
        created = meta.get("created_at")
        duration_minutes = 0.0
        if created:
            try:
                start = datetime.fromisoformat(created) if isinstance(created, str) else created
                duration_minutes = (datetime.now(timezone.utc) - start).total_seconds() / 60
            except Exception:
                pass

        # Get user info for notification preferences
        user_info = get_user_by_id(user_id)
        channel = "email"
        phone = None
        user_email = meta.get("user_email")
        if user_info:
            channel = user_info.get("notification_channel", "email")
            phone = user_info.get("phone_number")
            user_email = user_email or user_info.get("email")

        # Send email if channel is email or both
        if user_email and channel in ("email", "both"):
            await send_session_complete_email(
                to_email=user_email,
                session_id=session_id,
                total_applied=total_applied,
                total_failed=total_failed,
                total_skipped=total_skipped,
                top_companies=top_companies,
                avg_fit_score=0.0,
                duration_minutes=duration_minutes,
            )

        # Send SMS if channel is sms or both and phone exists
        if phone and channel in ("sms", "both"):
            await send_session_complete_sms(
                to_phone=phone,
                session_id=session_id,
                total_applied=total_applied,
                total_failed=total_failed,
            )
    except Exception:
        logger.warning("Failed to send completion notifications for %s", session_id, exc_info=True)


STATUS_MESSAGES = {
    "intake": "Setting up your job hunt session...",
    "coaching": "Your Career Coach is reviewing your resume — this usually takes about a minute...",
    "discovering": "Searching job boards for roles that match your profile...",
    "scoring": "Ranking jobs by how well they match your experience...",
    "tailoring": "Customizing your resume for your top matches...",
    "awaiting_review": "Your shortlist is ready — pick the jobs you'd like to apply to",
    "applying": "Submitting your applications...",
    "verifying": "Double-checking that applications went through...",
    "reporting": "Wrapping up and preparing your session summary...",
    "completed": "All done! Your session is complete",
    "failed": "Something went wrong — check the details below",
}

RESUME_STATUS_BY_NODE = {
    "career_coach": "coaching",
    "discovery": "discovering",
    "scoring": "scoring",
    "resume_tailor": "tailoring",
    "shortlist_review": "awaiting_review",
    "application": "applying",
    "verification": "verifying",
    "reporting": "reporting",
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

    Uses LangGraph v2 streaming — interrupts arrive as data in the stream
    chunk (``chunk["interrupts"]``) instead of raising ``GraphInterrupt``.
    """
    async for chunk in graph.astream(input_state, config=config, stream_mode="values", version="v2"):
        # Yield to the event loop so health checks / SSE / API calls aren't starved
        await asyncio.sleep(0)

        state_snapshot = chunk["data"]
        interrupts = chunk.get("interrupts", ())

        status = state_snapshot.get("status", "unknown")

        # Update registry status
        _set_session_status(session_id, status)

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
                "message": "Your top matches are ready — select the jobs you'd like to apply to.",
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

        # Track application counts in registry + Postgres
        _set_session_counts(
            session_id,
            len(state_snapshot.get("applications_submitted", [])),
            len(state_snapshot.get("applications_failed", [])),
        )

        if status in ("completed", "failed"):
            summary = _serialize(state_snapshot.get("session_summary"))
            await _emit(session_id, "done", {
                "status": status,
                "session_summary": summary,
            })
            # Clear is_running on autopilot schedule if applicable
            meta = session_registry.get(session_id, {})
            ap_schedule_id = meta.get("autopilot_schedule_id")
            if ap_schedule_id:
                try:
                    from backend.shared.autopilot_store import mark_run_complete
                    await mark_run_complete(ap_schedule_id)
                except Exception:
                    logger.debug("Failed to clear autopilot is_running", exc_info=True)
            return None  # Terminal — no interrupt

        # v2 streaming: interrupts arrive as data, not exceptions
        if interrupts:
            for intr in interrupts:
                stage = intr.value.get("stage") if isinstance(intr.value, dict) else None
                if stage:
                    logger.info("Pipeline paused at interrupt '%s' for session %s", stage, session_id)
                    return stage
            return "unknown_interrupt"

    return None


async def _handle_shortlist_interrupt(session_id: str, graph: Any, config: dict) -> None:
    """Emit the shortlist_review SSE event when the pipeline pauses for review."""
    _set_session_status(session_id, "awaiting_review")
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
            "message": "Your shortlist is ready — choose which jobs to apply to.",
        })
    except Exception:
        logger.exception("Failed to emit shortlist review event for session %s", session_id)

    # Send approval email/SMS for autopilot sessions
    try:
        meta = session_registry.get(session_id, {})
        schedule_id = meta.get("autopilot_schedule_id")
        if schedule_id:
            from backend.shared.autopilot_runner import generate_approval_token
            from backend.shared.email_notifications import send_autopilot_approval_email
            from backend.shared.sms import send_autopilot_approval_sms
            from backend.shared.billing_store import get_user_by_id

            user_id = meta.get("user_id")
            jobs_found = len(top_scored) if top_scored else 0
            token = generate_approval_token(schedule_id, session_id)

            # Get user info for notification routing
            user_info = get_user_by_id(user_id) if user_id else None
            user_email = meta.get("user_email")
            channel = "email"
            phone = None
            if user_info:
                channel = user_info.get("notification_channel", "email")
                phone = user_info.get("phone_number")
                user_email = user_email or user_info.get("email")

            if user_email and channel in ("email", "both"):
                await send_autopilot_approval_email(
                    to_email=user_email,
                    session_id=session_id,
                    schedule_id=schedule_id,
                    jobs_found=jobs_found,
                    approval_token=token,
                )

            if phone and channel in ("sms", "both"):
                schedule_name = meta.get("schedule_name", "My Job Search")
                await send_autopilot_approval_sms(
                    to_phone=phone,
                    schedule_name=schedule_name,
                    jobs_found=jobs_found,
                    session_id=session_id,
                )
    except Exception:
        logger.debug("Failed to send approval notifications for %s", session_id, exc_info=True)


async def _run_pipeline(
    session_id: str,
    request_body: StartSessionRequest,
    graph: Any,
    user_id: str = "",
) -> None:
    """Execute the LangGraph pipeline and emit SSE events as agents complete.

    Runs as a background task so the POST /api/sessions response returns
    immediately with the session_id. Handles interrupt detection for HITL
    gates (coach review, shortlist review).
    """
    # Register the emit callback so agents can send SSE events directly
    register_emitter(session_id, _emit)

    try:
        # Resume persistence now happens synchronously in start_session()
        # before spawning this background task (no race condition).

        # Build the initial state
        initial_state: Dict[str, Any] = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "keywords": request_body.keywords,
            "locations": request_body.locations,
            "remote_only": request_body.remote_only,
            "salary_min": request_body.salary_min,
            "search_radius": request_body.search_radius,
            "resume_text": request_body.resume_text or "",
            "resume_file_path": request_body.resume_file_path,
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
            "application_retry_counts": {},
            "active_retry_job_ids": [],
            "agent_statuses": {},
            "human_messages": [],
            "steering_mode": "status",
            "steering_messages_processed": 0,
            "pending_supervisor_response": None,
            "pending_supervisor_directives": [],
            "pause_requested": False,
            "pause_resume_node": None,
            "status_before_pause": None,
            "skip_next_job_requested": False,
            "pending_coach_review_input": None,
            "pending_shortlist_review_input": None,
            "coach_chat_history": [],
            "messages": [],
            "errors": [],
            "consecutive_failures": 0,
            "applications_used": 0,
            "job_urls": request_body.job_urls or [],
            "session_config": (
                request_body.config.model_dump()
                if request_body.config
                else None
            ),
        }

        # Quick Apply: when job_urls are provided, auto-set discovery_mode
        # and skip coach review (user wants fast path to applications)
        if initial_state["job_urls"]:
            cfg = initial_state.get("session_config") or {}
            cfg["discovery_mode"] = "manual_urls"
            initial_state["session_config"] = cfg
            prefs = initial_state.get("preferences") or {}
            prefs["_skip_coach_review"] = True
            initial_state["preferences"] = prefs

        await _emit(session_id, "status", {
            "status": "intake",
            "message": "Starting your job hunt session...",
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

                _set_session_status(session_id, "awaiting_coach_review")

                await _emit(session_id, "coach_review", {
                    "status": "awaiting_coach_review",
                    "coach_output": _serialize(coach_output) if coach_output else None,
                    "coached_resume": channel_values.get("coached_resume", ""),
                    "coach_chat_history": _serialize(channel_values.get("coach_chat_history", [])),
                    "message": "Your coached resume is ready for review. Approve it to start searching for jobs.",
                })
            except Exception:
                logger.exception("Failed to emit coach review event for session %s", session_id)

            # Do NOT unregister emitter or send "done" — pipeline will resume
            return

        if interrupt_stage == "shortlist_review":
            await _handle_shortlist_interrupt(session_id, graph, config)
            return

        # Terminal run (completed/failed): release emitter and task queue slot.
        if session_registry.get(session_id, {}).get("status") in {"completed", "failed"}:
            unregister_emitter(session_id)
            await _release_task_slot(session_id)

            # Send session-complete email notification (best-effort)
            await _send_completion_notifications(session_id)

    except Exception as exc:
        logger.exception("Pipeline error for session %s", session_id)
        _set_session_status(session_id, "failed")
        await _emit(session_id, "error", {
            "message": "An internal error occurred",
            "session_id": session_id,
        })
        await _emit(session_id, "done", {
            "status": "failed",
            "error": "An internal error occurred",
        })
        unregister_emitter(session_id)
        await _release_task_slot(session_id)
        await _send_completion_notifications(session_id)


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

        if session_registry.get(session_id, {}).get("status") in {"completed", "failed"}:
            unregister_emitter(session_id)

    except Exception as exc:
        logger.exception("Pipeline resume error for session %s", session_id)
        _set_session_status(session_id, "failed")
        await _emit(session_id, "error", {
            "message": "An internal error occurred",
            "session_id": session_id,
        })
        await _emit(session_id, "done", {
            "status": "failed",
            "error": "An internal error occurred",
        })
        unregister_emitter(session_id)
        await _release_task_slot(session_id)
        await _send_completion_notifications(session_id)
    finally:
        if session_registry.get(session_id, {}).get("status") in {"completed", "failed"}:
            unregister_emitter(session_id)


async def _resume_stalled_pipeline(session_id: str, graph: Any, config: dict) -> None:
    """Resume a pipeline that was interrupted mid-run (not at a HITL gate).

    Uses None as input to continue from the last checkpoint.
    """
    register_emitter(session_id, _emit)

    try:
        interrupt_stage = await _stream_graph(session_id, graph, config, None)

        if interrupt_stage == "coach_review":
            vals = (await graph.aget_state(config)).values
            _set_session_status(session_id, "awaiting_coach_review")
            await _emit(session_id, "coach_review", {
                "status": "awaiting_coach_review",
                "coach_output": _serialize(vals.get("coach_output")),
                "coached_resume": vals.get("coached_resume", ""),
                "coach_chat_history": _serialize(vals.get("coach_chat_history", [])),
                "message": "Your coached resume is ready for review.",
            })
            return

        if interrupt_stage == "shortlist_review":
            await _handle_shortlist_interrupt(session_id, graph, config)
            return

    except Exception as exc:
        logger.exception("Stalled pipeline resume failed for session %s", session_id)
        _set_session_status(session_id, "failed")
        await _emit(session_id, "error", {"message": "An internal error occurred", "session_id": session_id})
        await _emit(session_id, "done", {"status": "failed", "error": "An internal error occurred"})
        unregister_emitter(session_id)
    finally:
        if session_registry.get(session_id, {}).get("status") in {"completed", "failed"}:
            unregister_emitter(session_id)


# ---------------------------------------------------------------------------
# Snapshot synthesis (for reconnect after backend restart)
# ---------------------------------------------------------------------------

async def _synthesise_snapshot(session_id: str, checkpointer, graph=None):
    """Yield synthetic SSE events from durable checkpoint state.

    Called when ``event_logs`` is empty (backend restarted) so the frontend
    can hydrate without having received the original live events.
    """
    try:
        config = {"configurable": {"thread_id": session_id}}
        state = await checkpointer.aget(config)
        if state is None:
            return

        # Extract channel_values from checkpoint
        cp = state
        if hasattr(state, "checkpoint"):
            cp = state.checkpoint
        cv = cp.get("channel_values", cp) if isinstance(cp, dict) else cp
        if not isinstance(cv, dict):
            return

        # Determine true status (check for HITL interrupts)
        status = cv.get("status", "unknown")
        if graph is not None:
            try:
                graph_state = await graph.aget_state(config)
                next_nodes = getattr(graph_state, "next", ()) or ()
                if "coach_review" in next_nodes:
                    status = "awaiting_coach_review"
                elif "shortlist_review" in next_nodes:
                    status = "awaiting_review"
            except Exception:
                logger.debug("Could not check interrupt status for %s", session_id)

        # Update registry with correct status
        _set_session_status(session_id, status)

        # Emit status event
        status_data = {
            "status": status,
            "message": STATUS_MESSAGES.get(status, status),
            "keywords": cv.get("keywords", []),
        }
        yield f"event: status\ndata: {json.dumps(_serialize(status_data))}\n\n"

        # Emit coach_review if coach output exists and session is at that stage
        coach_output = cv.get("coach_output")
        if coach_output:
            coach_data = {
                "status": status,
                "coach_output": _serialize(coach_output),
                "coached_resume": cv.get("coached_resume", ""),
                "coach_chat_history": _serialize(cv.get("coach_chat_history", [])),
                "message": "Resume coaching complete.",
            }
            yield f"event: coach_review\ndata: {json.dumps(coach_data)}\n\n"

        # Emit shortlist_review if scored jobs exist
        scored_jobs = cv.get("scored_jobs", [])
        if scored_jobs:
            top_scored = sorted(
                scored_jobs,
                key=lambda sj: sj.score if hasattr(sj, "score") else sj.get("score", 0),
                reverse=True,
            )[:MAX_APPLICATION_JOBS]
            shortlist_data = {
                "status": status,
                "scored_jobs": _serialize(top_scored),
                "tailored_resumes": _serialize(cv.get("tailored_resumes", {})),
                "message": "Shortlist ready for review.",
            }
            yield f"event: shortlist_review\ndata: {json.dumps(shortlist_data)}\n\n"

        # Emit done for terminal sessions
        if status in ("completed", "failed"):
            done_data = {
                "status": status,
                "session_summary": _serialize(cv.get("session_summary")),
                "applications_submitted": _serialize(cv.get("applications_submitted", [])),
                "applications_failed": _serialize(cv.get("applications_failed", [])),
            }
            yield f"event: done\ndata: {json.dumps(done_data)}\n\n"

    except Exception:
        logger.exception("Failed to synthesise snapshot for session %s", session_id)


# ---------------------------------------------------------------------------
# SSE event generator
# ---------------------------------------------------------------------------

async def _event_generator(session_id: str, checkpointer=None, graph=None):
    """Yield SSE frames: first replay stored events, then stream live.

    Each connected client gets its own subscriber queue so multiple tabs
    or reconnects work independently. Stored events are replayed first,
    then live events stream from the per-subscriber queue.

    If ``event_logs`` is empty (e.g. after backend restart), synthesises
    events from the durable checkpointer state so the frontend can
    fully hydrate.
    """
    # Create a dedicated queue for this subscriber
    subscriber_queue: asyncio.Queue = asyncio.Queue()
    if session_id not in sse_subscribers:
        sse_subscribers[session_id] = []
    sse_subscribers[session_id].append(subscriber_queue)

    try:
        stored = list(event_logs.get(session_id, []))

        # Phase 0: If no stored events, synthesise from checkpointer
        if not stored and checkpointer is not None:
            async for frame in _synthesise_snapshot(session_id, checkpointer, graph):
                yield frame
                # If we emitted a done event, we're finished
                if 'event: done\n' in frame:
                    return

        # Phase 1: Replay all previously stored events
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

async def _load_sessions_from_db(checkpointer) -> Dict[str, dict]:
    """Load session metadata from the checkpointer's Postgres table.

    Queries for all distinct thread_ids and extracts metadata from their
    initial input checkpoint (step=-1) and latest checkpoint.
    """
    pool = getattr(checkpointer, "_pool", None) or getattr(checkpointer, "conn", None)
    if pool is None:
        return {}

    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # Get initial input (step -1) and latest checkpoint for each session
                await cur.execute("""
                    WITH latest AS (
                        SELECT DISTINCT ON (thread_id)
                            thread_id,
                            metadata::text as meta
                        FROM checkpoints
                        WHERE checkpoint_ns = ''
                        ORDER BY thread_id, checkpoint_id DESC
                    ),
                    initial AS (
                        SELECT
                            thread_id,
                            metadata::text as meta
                        FROM checkpoints
                        WHERE checkpoint_ns = ''
                          AND metadata->>'source' = 'input'
                    )
                    SELECT
                        l.thread_id,
                        l.meta as latest_meta,
                        i.meta as initial_meta
                    FROM latest l
                    LEFT JOIN initial i ON l.thread_id = i.thread_id
                """)
                rows = await cur.fetchall()

        sessions: Dict[str, dict] = {}
        for row in rows:
            thread_id = row[0]
            try:
                latest = json.loads(row[1]) if row[1] else {}
                initial = json.loads(row[2]) if row[2] else {}

                # Extract input data from initial checkpoint
                start_input = (initial.get("writes") or {}).get("__start__", {})

                # Determine status from latest checkpoint writes
                latest_writes = latest.get("writes") or {}
                status = start_input.get("status", "unknown")
                for _node_name, node_writes in latest_writes.items():
                    if isinstance(node_writes, dict) and "status" in node_writes:
                        status = node_writes["status"]

                apps_submitted = 0
                apps_failed = 0
                for _node_name, node_writes in latest_writes.items():
                    if isinstance(node_writes, dict):
                        sub = node_writes.get("applications_submitted")
                        fail = node_writes.get("applications_failed")
                        if isinstance(sub, list):
                            apps_submitted = len(sub)
                        if isinstance(fail, list):
                            apps_failed = len(fail)

                sessions[thread_id] = {
                    "session_id": thread_id,
                    "status": status,
                    "keywords": start_input.get("keywords", []),
                    "locations": start_input.get("locations", []),
                    "remote_only": start_input.get("remote_only", False),
                    "salary_min": start_input.get("salary_min"),
                    "resume_text_snippet": (start_input.get("resume_text") or "")[:200],
                    "linkedin_url": start_input.get("linkedin_url"),
                    "applications_submitted": apps_submitted,
                    "applications_failed": apps_failed,
                    "created_at": start_input.get("created_at", ""),
                }
            except Exception:
                logger.debug("Failed to parse checkpoint for thread %s", thread_id, exc_info=True)

        return sessions
    except Exception:
        logger.debug("Failed to load sessions from DB", exc_info=True)
        return {}


@router.get("")
async def list_sessions(request: Request):
    """Return all sessions, merging persisted DB state with in-memory registry."""
    from backend.gateway.deps import get_current_user
    user = get_current_user(request)
    user_id = str(user["id"])

    include_archived = request.query_params.get("include_archived", "").lower() == "true"

    # Load persisted sessions from the sessions table (source of truth)
    db_sessions = {s["session_id"]: s for s in get_sessions_for_user(user_id, include_archived=include_archived)}

    # Merge in-memory registry entries that aren't in the DB yet (just-created sessions)
    # Snapshot to avoid RuntimeError if another coroutine mutates the dict mid-iteration
    for sid, s in dict(session_registry).items():
        if sid not in db_sessions and str(s.get("user_id", "")) == user_id:
            db_sessions[sid] = s

    # For sessions in both, use DB status but overlay live fields from registry
    for sid, db_s in db_sessions.items():
        reg = session_registry.get(sid)
        if reg and db_s["status"] not in ("completed", "failed"):
            # Only overlay non-status fields (DB status is authoritative)
            for key in ("applications_submitted", "applications_failed"):
                if reg.get(key, 0) > db_s.get(key, 0):
                    db_s[key] = reg[key]

    sessions = sorted(
        db_sessions.values(),
        key=lambda s: s.get("created_at", ""),
        reverse=True,
    )

    # Ensure is_autopilot is set (from DB column or in-memory autopilot_schedule_id)
    for s in sessions:
        if "is_autopilot" not in s:
            s["is_autopilot"] = bool(s.get("autopilot_schedule_id"))

    return sessions


@router.patch("/{session_id}/archive")
async def archive_session_endpoint(session_id: str, request: Request):
    """Archive or unarchive a session."""
    from backend.gateway.deps import get_current_user
    from backend.shared.session_store import archive_session, unarchive_session
    user = get_current_user(request)
    user_id = str(user["id"])

    body = await request.json()
    archived = body.get("archived", True)

    if archived:
        ok = archive_session(session_id, user_id)
    else:
        ok = unarchive_session(session_id, user_id)

    if not ok:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return {"ok": True}


@router.delete("/{session_id}")
async def delete_session_endpoint(session_id: str, request: Request):
    """Permanently delete a session and all associated data."""
    from backend.gateway.deps import get_current_user
    from backend.shared.session_store import delete_session
    user = get_current_user(request)
    user_id = str(user["id"])

    ok = delete_session(session_id, user_id)
    if not ok:
        return JSONResponse({"error": "Session not found"}, status_code=404)

    # Remove from in-memory registry if present
    session_registry.pop(session_id, None)
    return {"ok": True}


@router.post("")
async def start_session(body: StartSessionRequest, request: Request):
    """Create a new pipeline session and begin execution in the background."""
    session_id = str(uuid.uuid4())
    graph = request.app.state.graph
    from backend.gateway.deps import get_current_user
    user = get_current_user(request)
    user_id = str(user["id"])  # Ensure string — users.id is UUID, sessions.user_id is TEXT

    min_submitted = getattr(body.config, "minimum_submitted_applications", 0) if body.config else 0
    if min_submitted > 0 and not user.get("is_premium", False):
        raise HTTPException(
            status_code=403,
            detail="Minimum submitted applications is available for premium users only.",
        )

    # Enforce per-user concurrency limits via Redis task queue
    try:
        from backend.shared.task_queue import enqueue_session, mark_active
        enqueued = await enqueue_session(session_id, user_id)
        if not enqueued:
            raise HTTPException(
                status_code=429,
                detail="You already have the maximum number of active sessions. Wait for one to finish before starting another.",
            )
        await mark_active(session_id)
    except HTTPException:
        raise
    except Exception:
        # Redis unavailable — allow the request through (graceful degradation)
        logger.debug("Task queue unavailable — skipping concurrency check", exc_info=True)

    # Initialize event log and subscriber list
    event_logs[session_id] = []
    sse_subscribers[session_id] = []

    # Register session metadata immediately (before pipeline starts)
    session_meta = {
        "session_id": session_id,
        "user_id": user_id,
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
    session_registry[session_id] = session_meta
    upsert_session(session_id, session_meta)

    # Re-key the resume from the parse-time file UUID to this session_id.
    # parse-resume saved to Postgres keyed by file UUID; we copy it under session_id.
    file_uuid = body.resume_uuid  # Preferred: explicit UUID from parse-resume response
    if not file_uuid:
        logger.warning("No resume_uuid in start_session body for session %s (resume_file_path=%s)", session_id, body.resume_file_path)
    if not file_uuid and body.resume_file_path:
        # Legacy fallback: extract UUID from file path
        import os
        basename = os.path.basename(body.resume_file_path)
        file_uuid = basename.split(".")[0]
        logger.info("Using legacy resume_file_path to extract UUID: %s", file_uuid)

    if file_uuid:
        try:
            from backend.shared.resume_store import save_resume as _save_resume_db, get_resume as _get_resume_db
            row = _get_resume_db(file_uuid)
            if row:
                enc_data, ext = row
                _save_resume_db(session_id, enc_data, ext)
                logger.info("Resume re-keyed from %s to session %s", file_uuid, session_id)
            else:
                logger.error("No resume in Postgres for file_uuid %s — parse-resume may not have saved it", file_uuid)
        except Exception:
            logger.warning("Failed to re-key resume in start_session", exc_info=True)

    # Launch the pipeline as a background coroutine
    _spawn_background(_run_pipeline(session_id, body, graph, user_id=user_id))

    return {"session_id": session_id}


# ---------------------------------------------------------------------------
# Re-run: clone an existing session with same (or overridden) search params
# ---------------------------------------------------------------------------


from pydantic import BaseModel as _RerunBase


class RerunRequest(_RerunBase):
    """Optional overrides when re-running a session."""
    keywords: List[str] | None = None
    locations: List[str] | None = None
    remote_only: bool | None = None
    salary_min: int | None = None


@router.post("/{session_id}/rerun")
async def rerun_session(session_id: str, body: RerunRequest, request: Request):
    """Clone a completed/failed session with same params (or overrides) and launch."""
    from backend.gateway.deps import get_current_user
    from backend.shared.session_store import get_session_by_id
    from backend.shared.resume_store import get_resume as _get_resume_db, save_resume as _save_resume_db

    user = get_current_user(request)
    user_id = str(user["id"])
    graph = request.app.state.graph

    # Load original session
    original = get_session_by_id(session_id)
    if not original:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(original["user_id"]) != user_id:
        raise HTTPException(status_code=403, detail="Not your session")

    # Build params: use overrides if provided, else original values
    keywords = body.keywords if body.keywords is not None else original["keywords"]
    locations = body.locations if body.locations is not None else original["locations"]
    remote_only = body.remote_only if body.remote_only is not None else original["remote_only"]
    salary_min = body.salary_min if body.salary_min is not None else original["salary_min"]

    # Clone resume from original session
    resume_row = _get_resume_db(session_id)
    resume_text = original.get("resume_text_snippet", "")

    new_session_id = str(uuid.uuid4())

    # Enforce concurrency limits
    try:
        from backend.shared.task_queue import enqueue_session, mark_active
        enqueued = await enqueue_session(new_session_id, user_id)
        if not enqueued:
            raise HTTPException(
                status_code=429,
                detail="You already have the maximum number of active sessions.",
            )
        await mark_active(new_session_id)
    except HTTPException:
        raise
    except Exception:
        logger.debug("Task queue unavailable — skipping concurrency check", exc_info=True)

    event_logs[new_session_id] = []
    sse_subscribers[new_session_id] = []

    session_meta = {
        "session_id": new_session_id,
        "user_id": user_id,
        "status": "intake",
        "keywords": keywords,
        "locations": locations,
        "remote_only": remote_only,
        "salary_min": salary_min,
        "resume_text_snippet": resume_text[:200],
        "linkedin_url": original.get("linkedin_url"),
        "applications_submitted": 0,
        "applications_failed": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    session_registry[new_session_id] = session_meta
    upsert_session(new_session_id, session_meta)

    # Copy resume to new session
    if resume_row:
        enc_data, ext = resume_row
        _save_resume_db(new_session_id, enc_data, ext)
        logger.info("Resume cloned from %s to %s", session_id, new_session_id)

    # Build StartSessionRequest for the pipeline
    # Re-runs skip coach review + auto-approve shortlist (resume already coached)
    start_body = StartSessionRequest(
        keywords=keywords,
        locations=locations,
        remote_only=remote_only,
        salary_min=salary_min,
        resume_text=resume_text,
        linkedin_url=original.get("linkedin_url"),
        preferences={
            "_skip_coach_review": True,
            "_autopilot_auto_approve": True,
        },
    )

    _spawn_background(_run_pipeline(new_session_id, start_body, graph, user_id=user_id))

    return {"session_id": new_session_id}


@router.post("/{session_id}/kill")
async def kill_session(session_id: str, request: Request):
    """Force-complete a session, releasing both DB status and Redis concurrency slot."""
    from backend.gateway.deps import get_current_user
    from backend.shared.session_store import get_session_by_id, update_session_status

    user = get_current_user(request)
    user_id = str(user["id"])

    session = get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(session["user_id"]) != user_id:
        raise HTTPException(status_code=403, detail="Not your session")
    if session["status"] in ("completed", "failed"):
        return {"status": "already_done"}

    # Update DB
    update_session_status(session_id, "completed")
    # Release Redis concurrency slot
    await _release_task_slot(session_id)

    logger.info("Session %s killed by user %s", session_id, user_id)
    return {"status": "killed"}


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
    from backend.gateway.deps import get_current_user
    get_current_user(request)  # 401 if no authenticated user

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

    _spawn_background(_test_apply_single(
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
    from backend.orchestrator.agents.application import run_application_agent
    from backend.shared.models.schemas import JobListing, JobBoard, TailoredResume

    # Detect board from URL
    _url_lower = job_url.lower()
    if "linkedin.com" in _url_lower:
        _board = JobBoard.LINKEDIN
    elif "glassdoor.com" in _url_lower:
        _board = JobBoard.GLASSDOOR
    elif "ziprecruiter.com" in _url_lower:
        _board = JobBoard.ZIPRECRUITER
    else:
        _board = JobBoard.INDEED

    dummy_job = JobListing(
        id=f"test-{uuid.uuid4().hex[:6]}",
        title=job_title,
        company=company,
        location="Remote",
        url=job_url,
        board=_board,
    )

    state = {
        "session_id": session_id,
        "resume_text": resume_text or "No resume provided",
        "coached_resume": resume_text or "",
        "cover_letter_template": "",
        "resume_file_path": None,
        "discovered_jobs": [dummy_job],
        "scored_jobs": [],
        "tailored_resumes": {
            dummy_job.id: TailoredResume(
                job_id=dummy_job.id,
                original_text=resume_text or "",
                tailored_text=resume_text or "",
                fit_score=75,
                changes_made=["Generated from test-apply input resume"],
            )
        },
        "application_queue": [dummy_job.id],
        "applications_submitted": [],
        "applications_failed": [],
        "applications_skipped": [],
        "consecutive_failures": 0,
        "errors": [],
        "agent_statuses": {},
    }
    terminal_status = "failed"

    try:
        await _emit(session_id, "status", {
            "status": "applying",
            "message": f"Applying to {job_title} at {company}...",
        })

        result_state = await run_application_agent(state)
        submitted = result_state.get("applications_submitted") or []
        failed = result_state.get("applications_failed") or []
        skipped = set(result_state.get("applications_skipped") or [])

        result_status = "failed"
        result_error = None
        result_duration = None
        if submitted:
            first = submitted[0]
            result_status = "submitted"
            result_error = getattr(first, "error_message", None)
            result_duration = getattr(first, "duration_seconds", None)
        elif failed:
            first = failed[0]
            result_status = "failed"
            result_error = getattr(first, "error_message", None)
            result_duration = getattr(first, "duration_seconds", None)
        elif dummy_job.id in skipped:
            result_status = "skipped"
            result_error = "skipped"

        final_status = "completed" if result_status == "submitted" else "failed"
        terminal_status = final_status
        await _emit(session_id, "status", {
            "status": final_status,
            "message": f"Result: {result_status} — {result_error or 'OK'}",
        })
        await _emit(session_id, "done", {
            "status": final_status,
            "message": f"Application {result_status}",
            "error": result_error,
            "duration_seconds": result_duration,
        })

    except Exception as exc:
        logger.exception("Test apply failed for %s", session_id)
        await _emit(session_id, "error", {"message": "An internal error occurred"})
        await _emit(session_id, "done", {"status": "failed", "error": "An internal error occurred"})
        terminal_status = "failed"
    finally:
        _set_session_status(session_id, terminal_status)
        unregister_emitter(session_id)


def _overlay_db_app_counts(session_id: str, result: dict) -> dict:
    """Overlay live application counts from the application_results DB table.

    The checkpointer only persists state when the full LangGraph node completes,
    so mid-run the applications_submitted/failed arrays are empty.  The DB table
    is written immediately per-application, so it's always up to date.
    """
    try:
        from backend.shared.application_store import get_results_for_session
        entries = get_results_for_session(session_id)
        if entries:
            submitted = [e for e in entries if e["status"] == "submitted"]
            failed = [e for e in entries if e["status"] == "failed"]
            skipped = [e for e in entries if e["status"] == "skipped"]
            result["applications_submitted"] = submitted
            result["applications_failed"] = failed
            result["applications_skipped"] = len(skipped)
            result["applications_used"] = len(entries)
    except Exception:
        logger.debug("Failed to overlay DB app counts for %s", session_id, exc_info=True)
    return result


@router.get("/{session_id}")
async def get_session(session_id: str, request: Request):
    """Return session state from checkpointer, falling back to registry."""
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)

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

        # Strip fields that are too large or not needed by the frontend.
        HEAVY_KEYS = {"messages", "resume_text", "cover_letter_template"}
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

        # Overlay live application counts from the DB (checkpointer only
        # updates when the full application node completes, so mid-run the
        # counts would be stale/empty).
        if isinstance(result, dict):
            result = _overlay_db_app_counts(session_id, result)

        return result

    # Fall back to the session registry (keywords, status, etc.)
    meta = session_registry.get(session_id)
    if meta is not None:
        return _overlay_db_app_counts(session_id, dict(meta))

    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/{session_id}/skipped-jobs")
async def get_skipped_jobs(session_id: str, request: Request):
    """Return skipped jobs with enriched details for manual application."""
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)

    checkpointer = request.app.state.checkpointer
    config = {"configurable": {"thread_id": session_id}}

    try:
        state = await checkpointer.aget(config)
    except Exception:
        state = None

    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    checkpoint = state
    if hasattr(state, "checkpoint"):
        checkpoint = state.checkpoint
    if isinstance(checkpoint, dict) and "channel_values" in checkpoint:
        cv = checkpoint["channel_values"]
    else:
        cv = checkpoint

    skipped_ids = set(cv.get("applications_skipped") or [])
    if not skipped_ids:
        return {"skipped_jobs": []}

    # Build a lookup of all jobs from scored_jobs
    scored_jobs = cv.get("scored_jobs") or []
    job_map = {}
    for sj in scored_jobs:
        job = sj.job if hasattr(sj, "job") else sj.get("job", {})
        job_id = job.id if hasattr(job, "id") else job.get("id")
        if job_id:
            job_map[job_id] = _serialize(sj)

    # Also check discovered_jobs
    for dj in cv.get("discovered_jobs") or []:
        job_id = dj.id if hasattr(dj, "id") else dj.get("id")
        if job_id and job_id not in job_map:
            job_map[job_id] = {"job": _serialize(dj), "score": 0}

    tailored = cv.get("tailored_resumes") or {}
    cover_template = cv.get("cover_letter_template") or ""

    results = []
    for jid in skipped_ids:
        entry = job_map.get(jid)
        if not entry:
            continue
        tr = tailored.get(jid)
        results.append({
            **entry,
            "tailored_resume": _serialize(tr) if tr else None,
            "cover_letter_template": cover_template,
        })

    return {"skipped_jobs": results}


@router.get("/{session_id}/application-log")
async def get_application_log(session_id: str, request: Request):
    """Return all application attempts from the persistent DB table."""
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)

    from backend.shared.application_store import get_results_for_session
    entries = get_results_for_session(session_id)
    return {"entries": entries}


@router.get("/{session_id}/screenshot")
async def get_application_screenshot(session_id: str, path: str, request: Request):
    """Serve a confirmation screenshot file from disk."""
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)
    from pathlib import Path
    from fastapi.responses import FileResponse
    import tempfile
    allowed_dir = Path(tempfile.gettempdir(), "jobhunter_screenshots").resolve()
    real_path = Path(path).resolve()
    if not real_path.is_relative_to(allowed_dir):
        raise HTTPException(status_code=403, detail="Access denied")
    if not real_path.is_file():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(str(real_path), media_type="image/png")


@router.get("/{session_id}/checkpoints")
async def list_checkpoints(session_id: str, request: Request):
    """List all checkpoints for a session (for rewind UI)."""
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)

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
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)

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
        # Load user_id and metadata from DB (survives restarts)
        from backend.shared.session_store import get_session_by_id
        db_row = get_session_by_id(session_id)

        session_registry[session_id] = {
            "session_id": session_id,
            "user_id": db_row["user_id"] if db_row else cv.get("user_id", ""),
            "status": cv.get("status", "unknown"),
            "keywords": cv.get("keywords", []),
            "locations": cv.get("locations", []),
            "remote_only": cv.get("remote_only", False),
            "salary_min": cv.get("salary_min"),
            "resume_text_snippet": (cv.get("resume_text", "") or "")[:200],
            "linkedin_url": cv.get("linkedin_url"),
            "applications_submitted": len(cv.get("applications_submitted", [])),
            "applications_failed": len(cv.get("applications_failed", [])),
            "created_at": db_row["created_at"] if db_row else cv.get("created_at", ""),
        }
        logger.info("Recovered session %s from checkpointer (status=%s, user_id=%s)",
                     session_id, cv.get("status"), session_registry[session_id].get("user_id", "?"))

    # Ensure event log and subscriber list exist
    if session_id not in event_logs:
        event_logs[session_id] = []
    if session_id not in sse_subscribers:
        sse_subscribers[session_id] = []

    checkpointer = request.app.state.checkpointer
    graph = request.app.state.graph

    return StreamingResponse(
        _event_generator(session_id, checkpointer=checkpointer, graph=graph),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/{session_id}/coach-chat")
async def coach_chat(session_id: str, body: CoachChatRequest, request: Request):
    """Revise coached artifacts interactively while awaiting coach review."""
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)

    graph = request.app.state.graph
    config = {"configurable": {"thread_id": session_id}}

    try:
        graph_state = await graph.aget_state(config)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Session not found")

    next_nodes = getattr(graph_state, "next", ()) or ()
    if "coach_review" not in next_nodes:
        raise HTTPException(
            status_code=409,
            detail="Coach chat is only available while awaiting coach review",
        )

    values = graph_state.values if hasattr(graph_state, "values") else {}
    coach_output_raw = values.get("coach_output")
    if not coach_output_raw:
        raise HTTPException(status_code=409, detail="No coach output available yet")

    coach_output = (
        coach_output_raw
        if hasattr(coach_output_raw, "model_dump")
        else CoachOutput(**coach_output_raw)
    )
    chat_history = values.get("coach_chat_history") or []
    latest_message = body.message.strip()
    if not latest_message:
        raise HTTPException(status_code=400, detail="Message is required")

    result = await revise_coach_output(
        original_resume=str(values.get("resume_text") or ""),
        current_output=coach_output,
        latest_user_message=latest_message,
        chat_history=list(chat_history),
    )

    updated_output = result.coach_output
    state_update: Dict[str, Any] = {
        "coach_output": updated_output,
        "coached_resume": updated_output.rewritten_resume,
        "cover_letter_template": updated_output.cover_letter_template,
        "coach_chat_history": [
            {"role": "user", "text": latest_message},
            {"role": "agent", "text": result.response_message},
        ],
        "messages": [
            HumanMessage(content=latest_message),
            AIMessage(content=result.response_message),
        ],
        "human_messages": [latest_message],
    }
    await graph.aupdate_state(config, state_update)

    await _emit(session_id, "coach_review", {
        "status": "awaiting_coach_review",
        "coach_output": _serialize(updated_output),
        "coached_resume": updated_output.rewritten_resume,
        "coach_chat_history": _serialize((chat_history or []) + state_update["coach_chat_history"]),
        "message": result.response_message,
    })

    return {
        "status": "ok",
        "message": result.response_message,
        "coach_output": _serialize(updated_output),
        "coach_chat_history": _serialize((chat_history or []) + state_update["coach_chat_history"]),
    }


@router.post("/{session_id}/coach-review")
async def submit_coach_review(session_id: str, body: CoachReviewRequest, request: Request):
    """Resume the pipeline after the user reviews the coached resume."""
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)

    graph = request.app.state.graph
    config = {"configurable": {"thread_id": session_id}}

    # Build the human input that coach_review_gate's interrupt() will receive
    human_input: Dict[str, Any] = {"approved": body.approved}
    if body.edited_resume:
        human_input["edited_resume"] = body.edited_resume
    if body.feedback:
        human_input["feedback"] = body.feedback

    graph_state = await graph.aget_state(config)
    values = graph_state.values if hasattr(graph_state, "values") else {}
    if values.get("pause_requested"):
        await graph.aupdate_state(
            config,
            {
                "pending_coach_review_input": human_input,
                "status": "paused",
            },
        )
        _set_session_status(session_id, "paused")
        await _emit(session_id, "status", {
            "status": "paused",
            "message": "Coach review saved. Workflow is paused until you resume it.",
        })
        return {"status": "ok", "message": "Coach review saved while paused"}

    _set_session_status(session_id, "discovering")

    await _emit(session_id, "status", {
        "status": "discovering",
        "message": "Resume approved! Now searching for matching jobs...",
    })

    # Resume the pipeline with Command(resume=human_input)
    _spawn_background(_resume_pipeline(session_id, graph, resume_value=human_input))

    return {"status": "ok", "message": "Coach review submitted, pipeline resuming"}


@router.post("/{session_id}/steer")
async def steer_session(session_id: str, body: SteerRequest, request: Request):
    """Inject a steering message into the running session."""
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)

    graph = request.app.state.graph
    config = {"configurable": {"thread_id": session_id}}
    graph_state = await graph.aget_state(config)
    values = graph_state.values if hasattr(graph_state, "values") else {}
    judge_result = await preview_steering_message(values, body.message)

    steering_mode = body.mode.value if body.mode else None
    directives = [d.model_dump() for d in judge_result.directives]
    for directive in judge_result.directives:
        if directive.action == "set_mode" and directive.mode:
            steering_mode = directive.mode
            break

    next_nodes = getattr(graph_state, "next", ()) or ()
    resume_target = values.get("pause_resume_node")
    if "coach_review" in next_nodes:
        resume_target = "discovery"
    elif "shortlist_review" in next_nodes:
        resume_target = "application"

    try:
        state_update: Dict[str, Any] = {
            "human_messages": [body.message],
            "messages": [HumanMessage(content=body.message)],
        }
        if steering_mode:
            state_update["steering_mode"] = steering_mode
        for directive in judge_result.directives:
            if directive.action == "pause":
                state_update["pause_requested"] = True
                if values.get("status") and values.get("status") != "paused":
                    state_update["status_before_pause"] = values.get("status")
                if resume_target:
                    state_update["pause_resume_node"] = resume_target
            elif directive.action == "resume_workflow":
                state_update["pause_requested"] = False
                state_update["status_before_pause"] = None
                if resume_target:
                    state_update["status"] = RESUME_STATUS_BY_NODE.get(resume_target, values.get("status"))
            elif directive.action == "skip_next_job":
                state_update["skip_next_job_requested"] = True
            elif directive.action == "block_company" and directive.company_name:
                try:
                    from backend.shared.billing_store import get_blocked_companies, update_blocked_companies
                    current = get_blocked_companies(user["id"])
                    company = directive.company_name.strip()
                    if company.lower() not in current:
                        from backend.shared.billing_store import get_user_by_id
                        user_data = get_user_by_id(user["id"])
                        raw_list = user_data.get("blocked_companies", []) if user_data else []
                        raw_list.append(company)
                        update_blocked_companies(user["id"], raw_list)
                        logger.info("Blocked company %r for user %s via steering", company, user["id"])
                except Exception:
                    logger.warning("Failed to block company via steering", exc_info=True)
        await graph.aupdate_state(config, state_update)
    except Exception as exc:
        logger.exception("Failed to steer session %s", session_id)
        raise HTTPException(status_code=500, detail="Failed to process steering command")

    should_resume = any(
        directive.action == "resume_workflow"
        for directive in judge_result.directives
    )
    if "pause_gate" in next_nodes:
        _spawn_background(
            _resume_pipeline(
                session_id,
                graph,
                resume_value={"resume": should_resume},
            )
        )
    elif should_resume and "coach_review" in next_nodes and values.get("pending_coach_review_input"):
        await graph.aupdate_state(config, {"pending_coach_review_input": None})
        resumed_status = RESUME_STATUS_BY_NODE.get("discovery", "discovering")
        _set_session_status(session_id, resumed_status)
        await _emit(session_id, "status", {
            "status": resumed_status,
            "message": "Resuming after the saved coach review...",
        })
        _spawn_background(
            _resume_pipeline(
                session_id,
                graph,
                resume_value=values["pending_coach_review_input"],
            )
        )
    elif should_resume and "shortlist_review" in next_nodes and values.get("pending_shortlist_review_input"):
        await graph.aupdate_state(config, {"pending_shortlist_review_input": None})
        resumed_status = RESUME_STATUS_BY_NODE.get("application", "applying")
        _set_session_status(session_id, resumed_status)
        await _emit(session_id, "status", {
            "status": resumed_status,
            "message": "Resuming after the saved shortlist decision...",
        })
        _spawn_background(
            _resume_pipeline(
                session_id,
                graph,
                resume_value=values["pending_shortlist_review_input"],
            )
        )

    await _emit(session_id, "status", {
        "status": "steering",
        "message": judge_result.response_message,
        "directives": directives,
    })

    return {
        "status": "ok",
        "message": judge_result.response_message,
        "directives": directives,
    }


@router.post("/{session_id}/review")
async def review_shortlist(session_id: str, body: ReviewRequest, request: Request):
    """Resume the pipeline after HITL shortlist review."""
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)

    graph = request.app.state.graph
    config = {"configurable": {"thread_id": session_id}}

    # Build the human input that shortlist_review_gate's interrupt() will receive
    human_input: Dict[str, Any] = {
        "approved_job_ids": body.approved_job_ids,
        "feedback": body.feedback or "",
    }

    graph_state = await graph.aget_state(config)
    values = graph_state.values if hasattr(graph_state, "values") else {}
    if values.get("pause_requested"):
        await graph.aupdate_state(
            config,
            {
                "pending_shortlist_review_input": human_input,
                "status": "paused",
            },
        )
        _set_session_status(session_id, "paused")
        await _emit(session_id, "status", {
            "status": "paused",
            "message": "Shortlist decision saved. Workflow is paused until you resume it.",
        })
        return {"status": "ok", "approved_count": len(body.approved_job_ids)}

    _set_session_status(session_id, "applying")

    await _emit(session_id, "status", {
        "status": "applying",
        "message": f"Great picks! Applying to {len(body.approved_job_ids)} {'job' if len(body.approved_job_ids) == 1 else 'jobs'}...",
        "approved_count": len(body.approved_job_ids),
    })

    # Resume the pipeline with Command(resume=human_input)
    _spawn_background(_resume_pipeline(session_id, graph, resume_value=human_input))

    return {
        "status": "ok",
        "approved_count": len(body.approved_job_ids),
    }


@router.post("/{session_id}/login-complete")
async def confirm_login(session_id: str, request: Request):
    """Signal the application agent that the user has logged in to a job board."""
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)

    from backend.orchestrator.agents._login_sync import signal_login_complete

    signal_login_complete(session_id)
    logger.info("User confirmed login for session %s", session_id)

    return {"status": "ok", "message": "Login confirmation received"}


@router.post("/{session_id}/resume-intervention")
async def resume_intervention(session_id: str, request: Request):
    """Signal the application agent to continue after user intervention."""
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)
    try:
        import redis.asyncio as aioredis
        from backend.shared.config import get_settings
        settings = get_settings()
        redis_client = aioredis.from_url(settings.REDIS_URL)
        await redis_client.set(f"intervention:resume:{session_id}", "1", ex=600)
        await redis_client.close()
    except Exception as exc:
        logger.exception("Failed to signal resume for session %s", session_id)
        raise HTTPException(status_code=500, detail="Failed to signal resume")

    await _emit(session_id, "status", {
        "status": "applying",
        "message": "Thanks for helping out — resuming applications...",
    })

    return {"status": "ok", "message": "Intervention resume signal sent"}


class SubmitDecisionRequest(_BaseModel):
    decision: str = "submit"  # "submit" or "skip"


@router.post("/{session_id}/submit-decision")
async def submit_decision(session_id: str, body: SubmitDecisionRequest, request: Request):
    """Approve or skip a pending application submission."""
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)
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
        logger.exception("Failed to send decision for session %s", session_id)
        raise HTTPException(status_code=500, detail="Failed to send decision")

    action_msg = "Submitting your application..." if body.decision == "submit" else "Skipping this one — moving on..."
    await _emit(session_id, "status", {
        "status": "applying",
        "message": action_msg,
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
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)

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
        raise HTTPException(status_code=404, detail="Checkpoint not found")

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
    _set_session_status(session_id, "applying")

    await _emit(session_id, "status", {
        "status": "applying",
        "message": f"Rewinding session — restarting with {len(resume_value.get('approved_job_ids', []))} {'job' if len(resume_value.get('approved_job_ids', [])) == 1 else 'jobs'}...",
    })

    # Resume the pipeline from the rewound checkpoint
    _spawn_background(_resume_pipeline(
        session_id, graph, resume_value=resume_value, checkpoint_id=body.checkpoint_id
    ))

    return {
        "status": "ok",
        "checkpoint_id": body.checkpoint_id,
        "next_nodes": list(next_nodes),
        "message": f"Resuming from {next_nodes}",
    }


@router.post("/{session_id}/resume")
async def resume_session(session_id: str, request: Request):
    """Resume a stalled pipeline from where it left off.

    Handles two cases:
    1. Pipeline is at an interrupt (HITL gate) — re-emits the review event
       so the frontend can show the modal.
    2. Pipeline was mid-run when the backend restarted — continues execution
       from the last checkpoint.
    """
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)

    graph = request.app.state.graph
    config = {"configurable": {"thread_id": session_id}}

    try:
        graph_state = await graph.aget_state(config)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="No checkpoint found for this session")

    next_nodes = getattr(graph_state, "next", ()) or ()
    if not next_nodes:
        raise HTTPException(
            status_code=400,
            detail="Session has no pending nodes — it may already be complete.",
        )

    # Ensure event infrastructure exists
    if session_id not in event_logs:
        event_logs[session_id] = []
    sse_subscribers.setdefault(session_id, [])

    # Recover session_registry if needed
    vals = graph_state.values if hasattr(graph_state, "values") else {}
    if session_id not in session_registry:
        session_registry[session_id] = {
            "session_id": session_id,
            "status": vals.get("status", "unknown"),
            "keywords": vals.get("keywords", []),
            "locations": vals.get("locations", []),
            "remote_only": vals.get("remote_only", False),
            "salary_min": vals.get("salary_min"),
            "resume_text_snippet": (vals.get("resume_text", "") or "")[:200],
            "linkedin_url": vals.get("linkedin_url"),
            "applications_submitted": len(vals.get("applications_submitted", [])),
            "applications_failed": len(vals.get("applications_failed", [])),
            "created_at": vals.get("created_at", ""),
        }

    register_emitter(session_id, _emit)

    # Case 1: At an interrupt — re-emit the HITL event
    if "coach_review" in next_nodes:
        _set_session_status(session_id, "awaiting_coach_review")
        await _emit(session_id, "coach_review", {
            "status": "awaiting_coach_review",
            "coach_output": _serialize(vals.get("coach_output")),
            "coached_resume": vals.get("coached_resume", ""),
            "coach_chat_history": _serialize(vals.get("coach_chat_history", [])),
            "message": "Your coached resume is ready for review.",
        })
        return {"status": "ok", "next": list(next_nodes), "action": "awaiting_coach_review"}

    if "shortlist_review" in next_nodes:
        await _handle_shortlist_interrupt(session_id, graph, config)
        return {"status": "ok", "next": list(next_nodes), "action": "awaiting_review"}

    # Case 2: Not at an interrupt — continue the pipeline
    next_label = next_nodes[0] if next_nodes else "unknown"
    _set_session_status(session_id, vals.get("status", next_label))

    await _emit(session_id, "status", {
        "status": session_registry[session_id]["status"],
        "message": f"Resuming pipeline from {next_label}...",
    })

    # Continue execution (None input = resume from last checkpoint)
    _spawn_background(_resume_stalled_pipeline(session_id, graph, config))

    return {"status": "ok", "next": list(next_nodes), "action": f"resuming_{next_label}"}


# ---------------------------------------------------------------------------
# Resume file parsing (PDF / DOCX / TXT → plain text)
# ---------------------------------------------------------------------------

@router.post("/parse-resume")
async def parse_resume(request: Request, file: UploadFile = File(...)):
    """Extract plain text from an uploaded resume file."""
    from backend.gateway.deps import get_current_user
    get_current_user(request)  # 401 if not authenticated
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    suffix = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""

    # Enforce 10 MB file size limit
    MAX_RESUME_BYTES = 10 * 1024 * 1024
    raw = await file.read(MAX_RESUME_BYTES + 1)
    if len(raw) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume file exceeds 10 MB limit")

    # Validate file signatures (magic bytes)
    if suffix == "pdf" and not raw[:4].startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="File does not appear to be a valid PDF")
    if suffix == "docx" and not raw[:4].startswith(b"PK\x03\x04"):
        raise HTTPException(status_code=400, detail="File does not appear to be a valid DOCX")

    if suffix == "txt":
        text = raw.decode("utf-8", errors="replace")
    elif suffix == "pdf":
        import io
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise HTTPException(
                status_code=500,
                detail="PDF parsing dependency missing (install `pypdf`).",
            ) from exc
        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        # OCR fallback for image-based PDFs
        if not text.strip():
            try:
                import fitz
                import pytesseract
                from PIL import Image
                doc = fitz.open(stream=raw, filetype="pdf")
                ocr_parts = []
                for page in doc:
                    pix = page.get_pixmap(dpi=300)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    ocr_parts.append(pytesseract.image_to_string(img))
                text = "\n".join(ocr_parts)
            except Exception as ocr_err:
                logger.warning("OCR fallback failed: %s", ocr_err)
    elif suffix == "docx":
        import io
        try:
            from docx import Document
        except ImportError as exc:
            raise HTTPException(
                status_code=500,
                detail="DOCX parsing dependency missing (install `python-docx`).",
            ) from exc
        doc = Document(io.BytesIO(raw))
        text = "\n".join(p.text for p in doc.paragraphs)
    elif suffix == "doc":
        raise HTTPException(
            status_code=400,
            detail="Legacy .doc files are not supported. Please upload .docx, .pdf, or .txt.",
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{suffix}")

    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Could not extract any text from the file")

    # Save the resume file encrypted at rest on the filesystem.
    # Postgres persistence happens later in start_session() (keyed by session_id).
    import tempfile
    import os
    import uuid
    from backend.shared.resume_crypto import encrypt_and_save

    resume_dir = os.path.join(tempfile.gettempdir(), "jobhunter_resumes")
    os.makedirs(resume_dir, exist_ok=True)
    file_uuid = uuid.uuid4().hex
    plaintext_path = os.path.join(resume_dir, f"{file_uuid}.{suffix}")
    enc_path = encrypt_and_save(raw, plaintext_path)
    logger.info("Resume encrypted and saved to %s", enc_path)

    # Persist to Postgres immediately so resume survives deploys.
    # Keyed by the file UUID — start_session() will re-key it under the session_id.
    try:
        from backend.shared.resume_store import save_resume as _save_resume_db
        with open(enc_path, "rb") as ef:
            _save_resume_db(file_uuid, ef.read(), f".{suffix}")
    except Exception:
        logger.warning("Failed to persist resume to Postgres in parse-resume", exc_info=True)

    return {"text": text, "filename": file.filename, "file_path": enc_path, "resume_uuid": file_uuid}


# ---------------------------------------------------------------------------
# LinkedIn Profile Updater
# ---------------------------------------------------------------------------

class LinkedInUpdateRequest(_BaseModel):
    updates: list[dict]  # [{"section": "headline", "content": "..."}, ...]
    linkedin_url: str | None = None


@router.post("/{session_id}/linkedin-update")
async def start_linkedin_update(session_id: str, body: LinkedInUpdateRequest, request: Request):
    """Launch a guided LinkedIn profile update in a visible browser.

    The browser opens to LinkedIn login, waits for the user to log in
    and confirm, then applies updates one section at a time.
    """
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)
    if not body.updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    # Ensure SSE infrastructure exists for this session
    sse_subscribers.setdefault(session_id, [])
    event_logs.setdefault(session_id, [])

    # Register emitter so the linkedin tool can send SSE events
    register_emitter(session_id, _emit)

    # Launch in background
    async def _run_linkedin_update():
        try:
            from backend.browser.tools.linkedin_updater import update_linkedin_profile
            await update_linkedin_profile(
                session_id=session_id,
                updates=body.updates,
                linkedin_url=body.linkedin_url,
            )
        except Exception as exc:
            logger.exception("LinkedIn update task failed for session %s", session_id)
            await _emit(session_id, "linkedin_update_failed", {
                "step": "LinkedIn update failed due to an internal error",
                "error": "An internal error occurred",
            })
        finally:
            unregister_emitter(session_id)

    _spawn_background(_run_linkedin_update())

    return {"status": "ok", "message": "LinkedIn update started — open the browser and log in"}


# ---------------------------------------------------------------------------
# Resume file serving (for Skyvern file upload)
# ---------------------------------------------------------------------------

@router.get("/{session_id}/resume-file")
async def serve_resume_file(session_id: str, request: Request, token: str = ""):
    """Serve the decrypted resume PDF for Skyvern to download.

    Protected by a short-lived HMAC token generated by the application agent.
    The resume file path is stored in Redis when the token is generated.
    """
    import hashlib
    import hmac
    import os
    import tempfile
    import time

    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    from backend.shared.config import get_settings
    from backend.shared.redis_client import redis_client

    secret = (get_settings().NEXTAUTH_SECRET or "").encode()
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    try:
        payload, sig = token.rsplit(".", 1)
        expected = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected):
            raise HTTPException(status_code=403, detail="Invalid token")
        _sid, ts_str = payload.rsplit(":", 1)
        if time.time() - int(ts_str) > 3600:
            raise HTTPException(status_code=403, detail="Token expired")
    except (ValueError, IndexError):
        raise HTTPException(status_code=403, detail="Malformed token")

    # Always read from Postgres — the single source of truth.
    from backend.shared.resume_store import get_resume_bytes, get_latest_resume_for_user
    from backend.shared.session_store import get_session_by_id

    result = get_resume_bytes(session_id)
    if not result:
        # Fallback: re-keying from parse-resume UUID may have failed.
        # Look up the user's most recent resume instead.
        sess = get_session_by_id(session_id)
        if sess:
            result = get_latest_resume_for_user(sess["user_id"])
            if result:
                logger.warning(
                    "Resume not found for session %s — fell back to user's latest resume",
                    session_id,
                )
    if not result:
        raise HTTPException(status_code=404, detail="No resume file found")

    data, ext = result
    fd, tmp = tempfile.mkstemp(suffix=ext)
    os.write(fd, data)
    os.close(fd)
    return FileResponse(
        tmp,
        media_type="application/pdf",
        filename=f"resume{ext}",
        background=BackgroundTask(os.remove, tmp),
    )


# ---------------------------------------------------------------------------
# Gmail token storage (for automatic verification-code extraction)
# ---------------------------------------------------------------------------

@router.post("/{session_id}/gmail-token")
async def store_gmail_token_endpoint(session_id: str, request: Request):
    """Store a Gmail OAuth token so the agent can auto-extract verification codes."""
    from backend.gateway.deps import get_current_user, verify_session_owner
    user = get_current_user(request)
    await verify_session_owner(session_id, user, request)

    body = await request.json()
    access_token = body.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="access_token is required")

    from backend.shared.gmail_client import store_gmail_token

    await store_gmail_token(
        session_id=session_id,
        access_token=access_token,
        refresh_token=body.get("refresh_token"),
        client_id=body.get("client_id"),
        client_secret=body.get("client_secret"),
    )
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# TOTP verification code endpoint (called by Skyvern)
# ---------------------------------------------------------------------------

@router.post("/{session_id}/totp-code")
async def get_totp_code(session_id: str, request: Request):
    """Return a verification code extracted from the user's Gmail.

    Skyvern calls this URL when it encounters a TOTP/2FA challenge.
    We poll Gmail for recent verification emails and return the code.
    No auth required — Skyvern uses internal Railway network.
    """
    body = await request.json()
    task_id = body.get("task_id", "")
    logger.info("TOTP code request for session %s (task %s)", session_id, task_id)

    from backend.shared.gmail_client import poll_for_verification_code

    code = await poll_for_verification_code(
        session_id=session_id,
        company="",
        platform="",
        max_wait=90,
        poll_interval=8,
    )

    if code:
        logger.info("TOTP code found for session %s: %s***", session_id, code[:2])
        return {"verification_code": code}

    logger.warning("No TOTP code found for session %s", session_id)

    # Emit SSE event so the user sees the failure in the Live Status card
    await _emit(session_id, "verification_progress", {
        "agent": "applier",
        "message": "Could not extract verification code from Gmail — the code may have expired or no matching email was found.",
    })

    return {"verification_code": None}


# ---------------------------------------------------------------------------
# Failure screenshots
# ---------------------------------------------------------------------------


@router.get("/{session_id}/screenshots")
async def list_screenshots(session_id: str, request: Request):
    """List all persisted failure screenshots for a session."""
    from backend.shared.screenshot_store import get_screenshots_for_session
    screenshots = get_screenshots_for_session(session_id)
    return {"screenshots": screenshots}


@router.get("/{session_id}/screenshots/{screenshot_id}")
async def get_screenshot(session_id: str, screenshot_id: int, request: Request):
    """Serve a persisted failure screenshot by ID."""
    from backend.shared.screenshot_store import get_screenshot as _get_screenshot
    result = _get_screenshot(screenshot_id)
    if not result:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    image_data, content_type = result
    return Response(content=image_data, media_type=content_type)


@router.get("/{session_id}/artifacts")
async def list_artifacts(session_id: str, request: Request):
    """List all persisted Skyvern task artifacts for a session.

    Each artifact contains the full task result: status, failure_reason,
    extracted_information, screenshot URLs, and timestamps.
    """
    from backend.shared.screenshot_store import get_artifacts_for_session
    artifacts = get_artifacts_for_session(session_id)
    return {"artifacts": artifacts}
