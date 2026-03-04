"""LangGraph StateGraph for the 8-agent JobHunter pipeline.

Pipeline stages:
    intake -> career_coach -> [HITL: review coached resume]
           -> discovery (fan-out to 5 job boards) -> scoring
           -> resume_tailor -> [HITL: review shortlist]
           -> application (loop with circuit breaker) -> verification
           -> reporting

Architecture mirrors the mayo-clinic-validator graph: StateGraph with
Send API for parallel dispatch, interrupt() for HITL checkpoints, and
conditional edges for routing.
"""

from __future__ import annotations

import logging
from typing import List, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from backend.orchestrator.agents import (
    application,
    career_coach,
    discovery,
    intake,
    reporting,
    resume_tailor,
    scoring,
    verification,
)
from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.models.schemas import JobBoard

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JOB_BOARDS: list[str] = [board.value for board in JobBoard]

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
# HITL checkpoint 1 – user reviews the coached resume
# ---------------------------------------------------------------------------


async def coach_review_gate(state: JobHunterState) -> dict:
    """Suspend execution so the user can review the coached resume.

    The graph pauses here.  When the user approves (or edits) the resume
    via the API, the graph resumes and interrupt() returns their input.
    """
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
# Discovery – parallel fan-out to 5 job boards via Send API
# ---------------------------------------------------------------------------


async def discovery_board_node(state: JobHunterState) -> dict:
    """Run discovery for a single job board.

    The ``board`` key is injected into the state slice by the Send dispatch.
    Each board's results are appended via the ``operator.add`` reducer on
    ``discovered_jobs``.
    """
    return await discovery.run(state)


def dispatch_discovery(state: JobHunterState) -> List[Send]:
    """Fan-out: dispatch one Send per job board.

    Each Send carries the full state plus an extra ``board`` key so the
    discovery node knows which board to scrape.
    """
    sends = []
    for board in JOB_BOARDS:
        sends.append(
            Send(
                "discovery",
                {**state, "board": board},
            )
        )
    return sends


# ---------------------------------------------------------------------------
# Post-discovery aggregation & scoring
# ---------------------------------------------------------------------------


async def scoring_node(state: JobHunterState) -> dict:
    """Score and rank all discovered jobs against the user profile."""
    return await scoring.run(state)


def route_after_discovery(state: JobHunterState) -> str:
    """After discovery fan-in, always proceed to scoring."""
    if not state.get("discovered_jobs"):
        logger.warning("No jobs discovered – routing to reporting.")
        return "reporting"
    return "scoring"


# ---------------------------------------------------------------------------
# Resume tailoring
# ---------------------------------------------------------------------------


async def resume_tailor_node(state: JobHunterState) -> dict:
    """Tailor the coached resume for each top-scored job."""
    return await resume_tailor.run(state)


def route_after_scoring(state: JobHunterState) -> str:
    """After scoring, proceed to resume tailoring."""
    if not state.get("scored_jobs"):
        logger.warning("No scored jobs – routing to reporting.")
        return "reporting"
    return "resume_tailor"


# ---------------------------------------------------------------------------
# HITL checkpoint 2 – user reviews the shortlist
# ---------------------------------------------------------------------------


async def shortlist_review_gate(state: JobHunterState) -> dict:
    """Suspend execution so the user can review the shortlist.

    The user sees scored jobs + tailored resumes and selects which ones
    to actually apply to.
    """
    human_input = interrupt(
        {
            "session_id": state["session_id"],
            "stage": "shortlist_review",
            "scored_jobs": [
                sj.model_dump() for sj in (state.get("scored_jobs") or [])
            ],
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
    updates: dict = {}
    approved = human_input.get("approved_job_ids", [])
    if approved:
        updates["application_queue"] = approved
    if human_input.get("feedback"):
        updates["human_messages"] = [human_input["feedback"]]
    return updates


# ---------------------------------------------------------------------------
# Application loop with circuit breaker
# ---------------------------------------------------------------------------


async def application_node(state: JobHunterState) -> dict:
    """Apply to the next job in the queue via browser automation."""
    return await application.run(state)


def route_after_application(
    state: JobHunterState,
) -> Literal["application", "verification"]:
    """Decide whether to continue applying or move to verification.

    Circuit-breaker: if consecutive failures exceed the threshold, stop
    the loop early and proceed to verification/reporting.
    """
    consecutive = state.get("consecutive_failures", 0)
    if consecutive >= MAX_CONSECUTIVE_FAILURES:
        logger.warning(
            "Circuit breaker tripped after %d consecutive failures.",
            consecutive,
        )
        return "verification"

    queue = state.get("application_queue", [])
    submitted = {r.job_id for r in (state.get("applications_submitted") or [])}
    failed = {r.job_id for r in (state.get("applications_failed") or [])}
    skipped = set(state.get("applications_skipped") or [])
    done = submitted | failed | skipped

    remaining = [jid for jid in queue if jid not in done]
    if remaining:
        return "application"

    return "verification"


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
    g.add_node("coach_review", coach_review_gate)
    g.add_node("discovery", discovery_board_node)
    g.add_node("scoring", scoring_node)
    g.add_node("resume_tailor", resume_tailor_node)
    g.add_node("shortlist_review", shortlist_review_gate)
    g.add_node("application", application_node)
    g.add_node("verification", verification_node)
    g.add_node("reporting", reporting_node)

    # ---- Edges ----

    # 1. Entry
    g.add_edge(START, "intake")

    # 2. intake -> career_coach
    g.add_edge("intake", "career_coach")

    # 3. career_coach -> HITL gate (coach review)
    g.add_edge("career_coach", "coach_review")

    # 4. coach_review -> discovery fan-out (Send API)
    g.add_conditional_edges(
        "coach_review",
        dispatch_discovery,
        JOB_BOARDS,
    )

    # 5. discovery fan-in -> scoring (conditional in case 0 results)
    g.add_conditional_edges(
        "discovery",
        route_after_discovery,
        {"scoring": "scoring", "reporting": "reporting"},
    )

    # 6. scoring -> resume_tailor (conditional in case 0 scored)
    g.add_conditional_edges(
        "scoring",
        route_after_scoring,
        {"resume_tailor": "resume_tailor", "reporting": "reporting"},
    )

    # 7. resume_tailor -> HITL gate (shortlist review)
    g.add_edge("resume_tailor", "shortlist_review")

    # 8. shortlist_review -> first application
    g.add_edge("shortlist_review", "application")

    # 9. application loop with circuit breaker
    g.add_conditional_edges(
        "application",
        route_after_application,
        {"application": "application", "verification": "verification"},
    )

    # 10. verification -> reporting
    g.add_edge("verification", "reporting")

    # 11. reporting -> END
    g.add_edge("reporting", END)

    return g.compile(checkpointer=checkpointer)
