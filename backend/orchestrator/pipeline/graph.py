# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""LangGraph StateGraph for the JobHunter pipeline.

Pipeline stages:
    intake -> career_coach -> [HITL: review coached resume]
           -> discovery (sequential, single browser) -> scoring
           -> [HITL: review shortlist] -> resume_tailor
           -> application (loop with circuit breaker) -> verification
           -> backfill_prep (if submitted < max_jobs) -> discovery (loop)
           -> reporting

Self-correcting backfill: after verification, if submitted applications are
below the user's max_jobs target, the pipeline loops back through discovery →
scoring → tailoring → application → verification again, up to 3 rounds.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, List, Literal

import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from backend.shared.config import MAX_APPLICATION_JOBS
from backend.shared.event_bus import emit_agent_event

from backend.orchestrator.pipeline.backfill import should_backfill

from backend.orchestrator.agents import (
    application,
    career_coach,
    discovery,
    intake,
    qa,
    reporting,
    resume_tailor,
    scoring,
    verification,
    workflow_supervisor,
)
from backend.orchestrator.pipeline.state import JobHunterState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum consecutive application failures before the circuit breaker trips.
MAX_CONSECUTIVE_FAILURES = 3


# ===================================================================
# Node functions
# ===================================================================


async def intake_node(state: JobHunterState) -> dict:
    """Parse user inputs into a structured SearchConfig."""
    return await intake.run(state)


async def career_coach_node(state: JobHunterState) -> dict:
    """Analyse resume, rewrite, generate cover-letter template."""
    return await career_coach.run(state)


# ---------------------------------------------------------------------------
# HITL checkpoint 1 -- user reviews the coached resume
# ---------------------------------------------------------------------------


async def coach_review_gate(state: JobHunterState) -> dict:
    """Suspend execution so the user can review the coached resume.

    The graph pauses here.  When the user approves (or edits) the resume
    via the API, the graph resumes and interrupt() returns their input.
    If coaching failed, skip the review and proceed directly to discovery.
    """
    # If coaching failed, skip the HITL review and continue the pipeline
    agent_statuses = state.get("agent_statuses", {})
    if agent_statuses.get("career_coach") == "failed" or not state.get("coach_output"):
        logger.warning("Coaching failed or no output — skipping coach review")
        return {"status": "discovering"}

    human_input = interrupt(
        {
            "session_id": state["session_id"],
            "stage": "coach_review",
            "coached_resume": state.get("coached_resume"),
            "coach_output": (
                state["coach_output"].model_dump()
                if state.get("coach_output")
                else None
            ),
            "message": (
                "Please review your coached resume and cover-letter "
                "template.  Approve to continue or provide edits."
            ),
        }
    )

    # human_input expected shape:
    # {"approved": True/False, "edited_resume": "...", "feedback": "..."}
    updates: dict = {}
    if human_input.get("edited_resume"):
        updates["coached_resume"] = human_input["edited_resume"]
    if human_input.get("feedback"):
        updates["human_messages"] = [human_input["feedback"]]
    return updates


# ---------------------------------------------------------------------------
# Discovery -- sequential scraping through a single shared browser
# ---------------------------------------------------------------------------


async def discovery_node(state: JobHunterState) -> dict:
    """Scrape all job boards sequentially with a single browser process."""
    logger.info("Discovery node invoked — scraping all boards sequentially")
    return await discovery.run(state)


def _continue_to_discovery(state: JobHunterState) -> str:
    config = state.get("session_config")
    if config and isinstance(config, dict) and config.get("discovery_mode") == "manual_urls":
        return "scoring"
    if config and hasattr(config, "discovery_mode") and config.discovery_mode == "manual_urls":
        return "scoring"
    return "discovery"


def _continue_to_career_coach(state: JobHunterState) -> str:
    return "career_coach"


def _continue_after_discovery(state: JobHunterState) -> str:
    return route_after_discovery(state)


def _continue_after_scoring(state: JobHunterState) -> str:
    return route_after_scoring(state)


def _continue_to_auto_approve_gate(state: JobHunterState) -> str:
    return "auto_approve_gate"


def _continue_to_application(state: JobHunterState) -> str:
    config = state.get("session_config")
    if config and isinstance(config, dict) and config.get("application_mode") == "materials_only":
        return "reporting"
    if config and hasattr(config, "application_mode") and config.application_mode == "materials_only":
        return "reporting"
    return "application"


def _continue_after_application(state: JobHunterState) -> str:
    return route_after_application(state)


def _continue_to_reporting(state: JobHunterState) -> str:
    return "reporting"


def _continue_after_pause(state: JobHunterState) -> str:
    return str(state.get("pause_resume_node") or "reporting")


def make_workflow_supervisor_node(
    continue_to: Callable[[JobHunterState], str],
) -> Callable[[JobHunterState], dict]:
    async def _node(state: JobHunterState) -> dict:
        return await workflow_supervisor.run_workflow_supervisor(
            state,
            continue_to=continue_to(state),
        )

    return _node


async def pause_gate_node(state: JobHunterState) -> dict:
    """Pause the workflow until the user resumes or sends another steering message."""
    human_input = interrupt(
        {
            "session_id": state["session_id"],
            "stage": "workflow_pause",
            "message": state.get("pending_supervisor_response") or "Workflow paused.",
            "resume_target": state.get("pause_resume_node"),
        }
    )
    if human_input.get("resume"):
        return {
            "pause_requested": False,
            "status": state.get("status_before_pause") or state.get("status") or "applying",
            "status_before_pause": None,
        }
    return {}


# ---------------------------------------------------------------------------
# Post-discovery aggregation & scoring
# ---------------------------------------------------------------------------


async def scoring_node(state: JobHunterState) -> dict:
    """Score and rank all discovered jobs against the user profile."""
    discovered = state.get("discovered_jobs", [])
    logger.info(
        "Scoring node received %d total discovered jobs from all boards",
        len(discovered),
    )
    return await scoring.run(state)


def route_after_discovery(state: JobHunterState) -> str:
    """After discovery fan-in, always proceed to scoring."""
    discovered = state.get("discovered_jobs", [])
    if not discovered:
        logger.warning("No jobs discovered across any board -- routing to reporting.")
        return "reporting"
    logger.info(
        "Discovery complete: %d total jobs -- routing to scoring", len(discovered)
    )
    return "scoring"


def route_after_supervise_after_discovery(state: JobHunterState) -> str:
    if state.get("pause_requested"):
        return "pause_gate"
    return route_after_discovery(state)


# ---------------------------------------------------------------------------
# Resume tailoring
# ---------------------------------------------------------------------------


async def resume_tailor_node(state: JobHunterState) -> dict:
    """Tailor the coached resume for each top-scored job."""
    return await resume_tailor.run(state)


def route_after_scoring(state: JobHunterState) -> str:
    """After scoring, proceed to auto-approve gate (then shortlist review)."""
    if not state.get("scored_jobs"):
        logger.warning("No scored jobs -- routing to reporting.")
        return "reporting"
    return "auto_approve_gate"


def route_after_supervise_after_scoring(state: JobHunterState) -> str:
    if state.get("pause_requested"):
        return "pause_gate"
    return route_after_scoring(state)


# ---------------------------------------------------------------------------
# HITL checkpoint 2 -- user reviews the shortlist
# ---------------------------------------------------------------------------


async def auto_approve_gate(state: JobHunterState) -> dict:
    """If autopilot or backfill round, populate application_queue and skip shortlist review."""
    prefs = state.get("preferences") or {}
    is_autopilot = isinstance(prefs, dict) and prefs.get("_autopilot_auto_approve")
    is_backfill = state.get("backfill_rounds", 0) > 0

    if is_autopilot or is_backfill:
        all_scored = state.get("scored_jobs") or []
        # On backfill, only queue jobs not already attempted
        done_ids: set[str] = set()
        if is_backfill:
            done_ids = (
                {r.job_id for r in (state.get("applications_submitted") or [])}
                | {r.job_id for r in (state.get("applications_failed") or [])}
                | set(state.get("applications_skipped") or [])
            )
        top_scored = sorted(all_scored, key=lambda sj: sj.score, reverse=True)
        approved_ids = [
            str(sj.job.id) for sj in top_scored
            if str(sj.job.id) not in done_ids
        ][:MAX_APPLICATION_JOBS]
        label = "backfill" if is_backfill else "autopilot"
        logger.info(
            "Auto-approve gate (%s): approving %d jobs",
            label, len(approved_ids),
        )
        return {"application_queue": approved_ids, "consecutive_failures": 0}
    return {}


def _route_after_auto_approve_gate(state: JobHunterState) -> str:
    """Route to application (via supervise) if auto-approved or backfill, otherwise to shortlist_review."""
    prefs = state.get("preferences") or {}
    is_autopilot = isinstance(prefs, dict) and prefs.get("_autopilot_auto_approve")
    is_backfill = state.get("backfill_rounds", 0) > 0
    if is_autopilot or is_backfill:
        return "supervise_after_shortlist"
    return "shortlist_review"


_EXPIRED_PAGE_INDICATORS = [
    "no longer open", "no longer available", "no longer accepting",
    "job has expired", "position has been filled", "job has been removed",
    "this listing has expired", "posting has been removed",
    "this job is no longer available", "this position is no longer available",
]

# ATS domains where pages return 200 for expired jobs (need GET + content check)
_NEEDS_CONTENT_CHECK = ("greenhouse.io", "job-boards.greenhouse.io", "lever.co")


async def _validate_job_urls(scored_jobs: list, session_id: str = "") -> list:
    """Validate job URLs via HTTP HEAD and filter out dead links.

    Returns only scored jobs whose URLs return a 2xx/3xx status.
    For Greenhouse/Lever URLs, also does a GET and checks page content for
    expired-job indicators (these sites return 200 for expired pages).
    """
    if not scored_jobs:
        return scored_jobs

    async def _check_url(sj) -> tuple:
        """Returns (scored_job, is_alive)."""
        url = sj.job.url if hasattr(sj.job, "url") else sj.get("job", {}).get("url", "")
        if not url:
            return (sj, False)
        title = sj.job.title if hasattr(sj.job, "title") else "unknown"
        try:
            needs_content = any(domain in url for domain in _NEEDS_CONTENT_CHECK)
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=10.0,
                headers={"User-Agent": "Mozilla/5.0 (JobHunterAgent URL Validator)"},
            ) as client:
                if needs_content:
                    # GET for ATS pages that return 200 for expired jobs
                    resp = await client.get(url)
                else:
                    resp = await client.head(url)
                    if resp.status_code == 405:
                        resp = await client.get(url)
                alive = resp.status_code < 400
                if not alive:
                    logger.info(
                        "URL validation: %s (%s) returned %d — removing from shortlist",
                        url, title, resp.status_code,
                    )
                    return (sj, False)
                # Content-based expired check for ATS pages
                if needs_content and alive:
                    body = resp.text[:2000].lower()
                    for indicator in _EXPIRED_PAGE_INDICATORS:
                        if indicator in body:
                            logger.info(
                                "URL validation: %s (%s) page says '%s' — removing expired job",
                                url, title, indicator,
                            )
                            return (sj, False)
                return (sj, alive)
        except Exception as exc:
            logger.info(
                "URL validation: %s (%s) unreachable (%s) — removing from shortlist",
                url, title, exc,
            )
            return (sj, False)

    results = await asyncio.gather(*[_check_url(sj) for sj in scored_jobs])
    valid = [sj for sj, alive in results if alive]
    removed = len(scored_jobs) - len(valid)
    if removed:
        logger.info(
            "URL validation removed %d/%d dead links for session %s",
            removed, len(scored_jobs), session_id,
        )
        if session_id:
            await emit_agent_event(session_id, "url_validation", {
                "total": len(scored_jobs),
                "valid": len(valid),
                "removed": removed,
            })
    return valid


async def shortlist_review_gate(state: JobHunterState) -> dict:
    """Suspend execution so the user can review the shortlist.

    The user sees scored jobs + tailored resumes and selects which ones
    to actually apply to.
    """
    # Only show the top scored jobs (sorted by score desc) to the user.
    all_scored = state.get("scored_jobs") or []
    top_scored = sorted(all_scored, key=lambda sj: sj.score, reverse=True)[:MAX_APPLICATION_JOBS]

    # Validate URLs — remove dead/expired links before showing to user
    session_id = state.get("session_id", "")
    top_scored = await _validate_job_urls(top_scored, session_id)

    # Re-rank after filtering (already sorted, but re-slice to MAX)
    top_scored = top_scored[:MAX_APPLICATION_JOBS]

    human_input = interrupt(
        {
            "session_id": state["session_id"],
            "stage": "shortlist_review",
            "scored_jobs": [sj.model_dump() for sj in top_scored],
            "message": (
                "Review the shortlist below.  Select jobs to apply to, "
                "or provide feedback to refine the results."
            ),
        }
    )

    # human_input expected shape:
    # {"approved_job_ids": [...], "feedback": "..."}
    updates: dict = {"consecutive_failures": 0}  # Reset circuit breaker on retry
    approved = human_input.get("approved_job_ids", [])
    if approved:
        if len(approved) > MAX_APPLICATION_JOBS:
            logger.info(
                "Capping approved jobs from %d to %d", len(approved), MAX_APPLICATION_JOBS
            )
            approved = approved[:MAX_APPLICATION_JOBS]
        updates["application_queue"] = approved
    if human_input.get("feedback"):
        updates["human_messages"] = [human_input["feedback"]]
    return updates


# ---------------------------------------------------------------------------
# Application loop with circuit breaker
# ---------------------------------------------------------------------------


async def application_node(state: JobHunterState) -> dict:
    """Apply to jobs in the queue via Playwright browser automation."""
    return await application.run(state)


def route_after_application(
    state: JobHunterState,
) -> Literal["application", "verification", "shortlist_review"]:
    """Decide whether to continue applying, retry, or move to verification.

    Circuit-breaker: if consecutive failures exceed the threshold AND there
    are remaining jobs, return to shortlist review. If all jobs are done
    (even if all failed), proceed to verification so the summary is generated.
    """
    queue = state.get("application_queue", [])
    submitted = {r.job_id for r in (state.get("applications_submitted") or [])}
    failed = {r.job_id for r in (state.get("applications_failed") or [])}
    skipped = set(state.get("applications_skipped") or [])
    done = submitted | failed | skipped

    remaining = [jid for jid in queue if jid not in done]

    # All jobs processed — always proceed to verification/summary
    if not remaining:
        return "verification"

    consecutive = state.get("consecutive_failures", 0)
    if consecutive >= MAX_CONSECUTIVE_FAILURES:
        logger.warning(
            "Circuit breaker tripped after %d consecutive failures -- "
            "returning to shortlist review for retry.",
            consecutive,
        )
        return "shortlist_review"

    return "application"


def route_after_supervise_after_application(
    state: JobHunterState,
) -> Literal["pause_gate", "application", "verification", "shortlist_review"]:
    if state.get("pause_requested"):
        return "pause_gate"
    return route_after_application(state)


def route_after_supervise_after_simple_stage(
    state: JobHunterState,
    *,
    default_next: str,
) -> str:
    if state.get("pause_requested"):
        return "pause_gate"
    return default_next


def route_after_pause_gate(
    state: JobHunterState,
) -> Literal[
    "pause_gate",
    "career_coach",
    "discovery",
    "scoring",
    "resume_tailor",
    "shortlist_review",
    "application",
    "verification",
    "backfill_prep",
    "reporting",
]:
    if state.get("pause_requested"):
        return "pause_gate"

    target = state.get("pause_resume_node") or "reporting"
    allowed = {
        "career_coach",
        "discovery",
        "scoring",
        "resume_tailor",
        "shortlist_review",
        "application",
        "verification",
        "qa",
        "backfill_prep",
        "reporting",
    }
    if target not in allowed:
        logger.warning("Unknown pause resume target %s -- routing to reporting", target)
        return "reporting"
    return target  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Verification & reporting
# ---------------------------------------------------------------------------


async def verification_node(state: JobHunterState) -> dict:
    """Verify submitted applications (confirmation e-mails, status pages)."""
    return await verification.run(state)


async def qa_node(state: JobHunterState) -> dict:
    """Quality assurance: analyse failures and gate backfill decisions."""
    return await qa.run(state)


async def reporting_node(state: JobHunterState) -> dict:
    """Generate a session summary report."""
    return await reporting.run(state)


# ---------------------------------------------------------------------------
# Backfill (self-correcting loop)
# ---------------------------------------------------------------------------


def _get_max_jobs(state: JobHunterState) -> int:
    """Extract the user's max_jobs target from session config."""
    config = state.get("session_config")
    if config:
        cfg = config if isinstance(config, dict) else (
            config.model_dump() if hasattr(config, "model_dump") else {}
        )
        return cfg.get("max_jobs", 20) or 20
    return 20


async def backfill_prep_node(state: JobHunterState) -> dict:
    """Prepare state for a backfill round — collect seen IDs and bump counter."""
    submitted = len(state.get("applications_submitted") or [])
    max_jobs = _get_max_jobs(state)
    deficit = max_jobs - submitted
    rounds = state.get("backfill_rounds", 0)

    # Collect all job IDs we've already seen (for dedup in next discovery)
    seen_ids = [str(job.id) for job in (state.get("discovered_jobs") or [])]

    # Apply QA insights: remove boards that consistently fail
    qa_analysis = state.get("qa_analysis")
    boards_to_skip = []
    if qa_analysis and isinstance(qa_analysis, dict):
        boards_to_skip = qa_analysis.get("boards_to_skip", [])

    step_msg = f"Backfill round {rounds + 1}: need {deficit} more applications"
    if boards_to_skip:
        step_msg += f" (skipping: {', '.join(boards_to_skip)})"
        logger.info("QA boards_to_skip applied: %s", boards_to_skip)

    await emit_agent_event(state["session_id"], "backfill_progress", {
        "step": step_msg,
        "submitted": submitted,
        "target": max_jobs,
        "round": rounds + 1,
        "boards_to_skip": boards_to_skip,
    })

    # Update session config to exclude problematic boards
    updates: dict = {
        "backfill_rounds": rounds + 1,
        "discovered_job_ids_seen": seen_ids,
        "_prev_backfill_submitted": submitted,
        "consecutive_failures": 0,
        "status": "discovering",
    }

    if boards_to_skip:
        config = state.get("session_config")
        if config:
            cfg = config if isinstance(config, dict) else config.model_dump()
            current_boards = cfg.get("job_boards", [])
            filtered = [b for b in current_boards if b not in boards_to_skip]
            if filtered and len(filtered) < len(current_boards):
                from backend.shared.models.schemas import SessionConfig
                new_cfg = {**cfg, "job_boards": filtered}
                updates["session_config"] = SessionConfig(**new_cfg)
                logger.info("Backfill: filtered boards %s -> %s", current_boards, filtered)

    return updates


def _continue_after_verification(state: JobHunterState) -> str:
    return "qa"


def route_after_supervise_after_verification(state: JobHunterState) -> str:
    if state.get("pause_requested"):
        return "pause_gate"
    return "qa"


def route_after_qa(state: JobHunterState) -> str:
    """After QA, check analysis decision and backfill eligibility."""
    qa_analysis = state.get("qa_analysis")
    if qa_analysis and isinstance(qa_analysis, dict):
        if qa_analysis.get("decision") == "halt":
            logger.info("QA decision=halt — skipping backfill, routing to reporting")
            return "reporting"

    # Standard backfill check
    submitted = len(state.get("applications_submitted") or [])
    max_jobs = _get_max_jobs(state)

    if should_backfill(state, submitted, max_jobs):
        logger.info(
            "Backfill: %d/%d submitted, round %d — routing to backfill_prep",
            submitted, max_jobs, state.get("backfill_rounds", 0),
        )
        return "backfill_prep"
    return "reporting"


def _continue_after_qa(state: JobHunterState) -> str:
    return route_after_qa(state)


def route_after_supervise_after_qa(state: JobHunterState) -> str:
    if state.get("pause_requested"):
        return "pause_gate"
    return route_after_qa(state)


# ===================================================================
# Build the compiled graph
# ===================================================================


def build_graph(checkpointer=None):
    """Construct and compile the JobHunter StateGraph.

    Parameters
    ----------
    checkpointer : langgraph.checkpoint.base.BaseCheckpointSaver | None
        Optional checkpointer for durable HITL state persistence
        (e.g. ``PostgresCheckpointer`` or ``MemorySaver``).

    Returns
    -------
    langgraph.graph.state.CompiledStateGraph
        The compiled, ready-to-invoke graph.
    """
    g = StateGraph(JobHunterState)

    # ---- Register nodes ----
    g.add_node("intake", intake_node)
    g.add_node("career_coach", career_coach_node)
    g.add_node("supervise_after_intake", make_workflow_supervisor_node(_continue_to_career_coach))
    g.add_node("coach_review", coach_review_gate)
    g.add_node("supervise_after_coach_review", make_workflow_supervisor_node(_continue_to_discovery))
    g.add_node("discovery", discovery_node)
    g.add_node("supervise_after_discovery", make_workflow_supervisor_node(_continue_after_discovery))
    g.add_node("scoring", scoring_node)
    g.add_node("supervise_after_scoring", make_workflow_supervisor_node(_continue_after_scoring))
    g.add_node("resume_tailor", resume_tailor_node)
    g.add_node("auto_approve_gate", auto_approve_gate)
    g.add_node("supervise_after_tailor", make_workflow_supervisor_node(_continue_to_auto_approve_gate))
    g.add_node("shortlist_review", shortlist_review_gate)
    g.add_node("supervise_after_shortlist", make_workflow_supervisor_node(_continue_to_application))
    g.add_node("application", application_node)
    g.add_node("supervise_after_application", make_workflow_supervisor_node(_continue_after_application))
    g.add_node("verification", verification_node)
    g.add_node("supervise_after_verification", make_workflow_supervisor_node(_continue_after_verification))
    g.add_node("qa", qa_node)
    g.add_node("supervise_after_qa", make_workflow_supervisor_node(_continue_after_qa))
    g.add_node("backfill_prep", backfill_prep_node)
    g.add_node("pause_gate", pause_gate_node)
    g.add_node("supervise_after_pause", make_workflow_supervisor_node(_continue_after_pause))
    g.add_node("reporting", reporting_node)

    # ---- Edges ----

    # 1. Entry
    g.add_edge(START, "intake")

    # 2. intake -> career_coach
    g.add_edge("intake", "supervise_after_intake")
    g.add_conditional_edges(
        "supervise_after_intake",
        lambda state: route_after_supervise_after_simple_stage(state, default_next="career_coach"),
        {"career_coach": "career_coach", "pause_gate": "pause_gate"},
    )

    # 3. career_coach -> HITL gate (coach review)
    g.add_edge("career_coach", "coach_review")

    # 4. coach_review -> discovery (single node, sequential scraping)
    g.add_edge("coach_review", "supervise_after_coach_review")
    def _route_after_coach_review_supervise(state: JobHunterState) -> str:
        if state.get("pause_requested"):
            return "pause_gate"
        return _continue_to_discovery(state)

    g.add_conditional_edges(
        "supervise_after_coach_review",
        _route_after_coach_review_supervise,
        {"discovery": "discovery", "scoring": "scoring", "pause_gate": "pause_gate"},
    )

    # 5. discovery -> scoring (conditional in case 0 results)
    g.add_conditional_edges(
        "supervise_after_discovery",
        route_after_supervise_after_discovery,
        {"scoring": "scoring", "reporting": "reporting", "pause_gate": "pause_gate"},
    )
    g.add_edge("discovery", "supervise_after_discovery")

    # 6. scoring -> auto_approve_gate -> shortlist_review (conditional in case 0 scored)
    g.add_conditional_edges(
        "supervise_after_scoring",
        route_after_supervise_after_scoring,
        {"auto_approve_gate": "auto_approve_gate", "reporting": "reporting", "pause_gate": "pause_gate"},
    )
    g.add_edge("scoring", "supervise_after_scoring")

    # 7. auto_approve_gate -> shortlist_review or straight to resume_tailor (autopilot)
    g.add_conditional_edges(
        "auto_approve_gate",
        _route_after_auto_approve_gate,
        {"supervise_after_shortlist": "supervise_after_shortlist", "shortlist_review": "shortlist_review"},
    )

    # 8. shortlist_review -> resume_tailor (only tailor approved jobs)
    g.add_edge("shortlist_review", "supervise_after_shortlist")
    def _route_after_shortlist_supervise(state: JobHunterState) -> str:
        if state.get("pause_requested"):
            return "pause_gate"
        return "resume_tailor"

    g.add_conditional_edges(
        "supervise_after_shortlist",
        _route_after_shortlist_supervise,
        {"resume_tailor": "resume_tailor", "pause_gate": "pause_gate"},
    )

    # 9. resume_tailor -> application (or reporting for materials_only mode)
    g.add_edge("resume_tailor", "supervise_after_tailor")
    def _route_after_tailor_supervise(state: JobHunterState) -> str:
        if state.get("pause_requested"):
            return "pause_gate"
        return _continue_to_application(state)

    g.add_conditional_edges(
        "supervise_after_tailor",
        _route_after_tailor_supervise,
        {"application": "application", "reporting": "reporting", "pause_gate": "pause_gate"},
    )

    # 10. application loop with circuit breaker (retries go back to HITL gate)
    g.add_conditional_edges(
        "supervise_after_application",
        route_after_supervise_after_application,
        {
            "pause_gate": "pause_gate",
            "application": "application",
            "verification": "verification",
            "shortlist_review": "shortlist_review",
        },
    )
    g.add_edge("application", "supervise_after_application")

    # 11. verification -> QA -> reporting OR backfill_prep (self-correcting loop)
    g.add_edge("verification", "supervise_after_verification")
    g.add_conditional_edges(
        "supervise_after_verification",
        route_after_supervise_after_verification,
        {"qa": "qa", "pause_gate": "pause_gate"},
    )
    g.add_edge("qa", "supervise_after_qa")
    g.add_conditional_edges(
        "supervise_after_qa",
        route_after_supervise_after_qa,
        {"reporting": "reporting", "backfill_prep": "backfill_prep", "pause_gate": "pause_gate"},
    )
    g.add_edge("backfill_prep", "discovery")

    g.add_edge("pause_gate", "supervise_after_pause")
    g.add_conditional_edges(
        "supervise_after_pause",
        route_after_pause_gate,
        {
            "pause_gate": "pause_gate",
            "career_coach": "career_coach",
            "discovery": "discovery",
            "scoring": "scoring",
            "resume_tailor": "resume_tailor",
            "shortlist_review": "shortlist_review",
            "application": "application",
            "verification": "verification",
            "qa": "qa",
            "backfill_prep": "backfill_prep",
            "reporting": "reporting",
        },
    )

    # 12. reporting -> END
    g.add_edge("reporting", END)

    return g.compile(checkpointer=checkpointer)
