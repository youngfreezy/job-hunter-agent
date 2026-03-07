"""LangGraph StateGraph for the 8-agent JobHunter pipeline.

Pipeline stages:
    intake -> career_coach -> [HITL: review coached resume]
           -> discovery (sequential, single browser) -> scoring
           -> resume_tailor -> [HITL: review shortlist]
           -> application (loop with circuit breaker) -> verification
           -> reporting

Discovery scrapes all 5 job boards sequentially through a single shared
browser process.  Application uses Playwright for form filling.
"""

from __future__ import annotations

import logging
from typing import Callable, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from backend.shared.config import MAX_APPLICATION_JOBS

from backend.orchestrator.agents import (
    application,
    career_coach,
    discovery,
    intake,
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
    return "discovery"


def _continue_to_career_coach(state: JobHunterState) -> str:
    return "career_coach"


def _continue_after_discovery(state: JobHunterState) -> str:
    return route_after_discovery(state)


def _continue_after_scoring(state: JobHunterState) -> str:
    return route_after_scoring(state)


def _continue_to_shortlist_review(state: JobHunterState) -> str:
    return "shortlist_review"


def _continue_to_application(state: JobHunterState) -> str:
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
    """After scoring, proceed to resume tailoring."""
    if not state.get("scored_jobs"):
        logger.warning("No scored jobs -- routing to reporting.")
        return "reporting"
    return "resume_tailor"


def route_after_supervise_after_scoring(state: JobHunterState) -> str:
    if state.get("pause_requested"):
        return "pause_gate"
    return route_after_scoring(state)


# ---------------------------------------------------------------------------
# HITL checkpoint 2 -- user reviews the shortlist
# ---------------------------------------------------------------------------


async def shortlist_review_gate(state: JobHunterState) -> dict:
    """Suspend execution so the user can review the shortlist.

    The user sees scored jobs + tailored resumes and selects which ones
    to actually apply to.
    """
    # Only show the top scored jobs (sorted by score desc) to the user.
    all_scored = state.get("scored_jobs") or []
    top_scored = sorted(all_scored, key=lambda sj: sj.score, reverse=True)[:MAX_APPLICATION_JOBS]

    human_input = interrupt(
        {
            "session_id": state["session_id"],
            "stage": "shortlist_review",
            "scored_jobs": [sj.model_dump() for sj in top_scored],
            "tailored_resumes": {
                jid: tr.model_dump()
                for jid, tr in (state.get("tailored_resumes") or {}).items()
            },
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

    Circuit-breaker: if consecutive failures exceed the threshold, return
    to the shortlist review gate so the user can retry or adjust.
    """
    consecutive = state.get("consecutive_failures", 0)
    if consecutive >= MAX_CONSECUTIVE_FAILURES:
        logger.warning(
            "Circuit breaker tripped after %d consecutive failures -- "
            "returning to shortlist review for retry.",
            consecutive,
        )
        return "shortlist_review"

    queue = state.get("application_queue", [])
    submitted = {r.job_id for r in (state.get("applications_submitted") or [])}
    failed = {r.job_id for r in (state.get("applications_failed") or [])}
    skipped = set(state.get("applications_skipped") or [])
    done = submitted | failed | skipped

    remaining = [jid for jid in queue if jid not in done]
    if remaining:
        return "application"

    return "verification"


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


async def reporting_node(state: JobHunterState) -> dict:
    """Generate a session summary report."""
    return await reporting.run(state)


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
    g.add_node("supervise_after_tailor", make_workflow_supervisor_node(_continue_to_shortlist_review))
    g.add_node("shortlist_review", shortlist_review_gate)
    g.add_node("supervise_after_shortlist", make_workflow_supervisor_node(_continue_to_application))
    g.add_node("application", application_node)
    g.add_node("supervise_after_application", make_workflow_supervisor_node(_continue_after_application))
    g.add_node("verification", verification_node)
    g.add_node("supervise_after_verification", make_workflow_supervisor_node(_continue_to_reporting))
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
    g.add_conditional_edges(
        "supervise_after_coach_review",
        lambda state: route_after_supervise_after_simple_stage(state, default_next="discovery"),
        {"discovery": "discovery", "pause_gate": "pause_gate"},
    )

    # 5. discovery -> scoring (conditional in case 0 results)
    g.add_conditional_edges(
        "supervise_after_discovery",
        route_after_supervise_after_discovery,
        {"scoring": "scoring", "reporting": "reporting", "pause_gate": "pause_gate"},
    )
    g.add_edge("discovery", "supervise_after_discovery")

    # 6. scoring -> resume_tailor (conditional in case 0 scored)
    g.add_conditional_edges(
        "supervise_after_scoring",
        route_after_supervise_after_scoring,
        {"resume_tailor": "resume_tailor", "reporting": "reporting", "pause_gate": "pause_gate"},
    )
    g.add_edge("scoring", "supervise_after_scoring")

    # 7. resume_tailor -> HITL gate (shortlist review)
    g.add_edge("resume_tailor", "supervise_after_tailor")
    g.add_conditional_edges(
        "supervise_after_tailor",
        lambda state: route_after_supervise_after_simple_stage(state, default_next="shortlist_review"),
        {"shortlist_review": "shortlist_review", "pause_gate": "pause_gate"},
    )

    # 8. shortlist_review -> first application
    g.add_edge("shortlist_review", "supervise_after_shortlist")
    g.add_conditional_edges(
        "supervise_after_shortlist",
        lambda state: route_after_supervise_after_simple_stage(state, default_next="application"),
        {"application": "application", "pause_gate": "pause_gate"},
    )

    # 9. application loop with circuit breaker (retries go back to HITL gate)
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

    # 10. verification -> reporting
    g.add_edge("verification", "supervise_after_verification")
    g.add_conditional_edges(
        "supervise_after_verification",
        lambda state: route_after_supervise_after_simple_stage(state, default_next="reporting"),
        {"reporting": "reporting", "pause_gate": "pause_gate"},
    )

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
            "reporting": "reporting",
        },
    )

    # 11. reporting -> END
    g.add_edge("reporting", END)

    return g.compile(checkpointer=checkpointer)
