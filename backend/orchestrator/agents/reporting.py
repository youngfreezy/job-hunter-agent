"""Reporting Agent -- aggregates session data into a final summary."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.config import get_settings
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import (
    ApplicationResult,
    ScoredJob,
    SessionSummary,
)

logger = logging.getLogger(__name__)


class NextStepsResult(BaseModel):
    next_steps: List[str] = Field(description="3-5 actionable next steps for the candidate")

HAIKU_MODEL = "claude-haiku-4-5-20251001"


def _build_llm() -> ChatAnthropic:
    settings = get_settings()
    return ChatAnthropic(
        model=HAIKU_MODEL,
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=1024,
        temperature=0.4,
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

NEXT_STEPS_SYSTEM = """\
You are a career strategy assistant. Given a summary of a job-hunting session,
generate a list of 3-5 actionable next steps the candidate should take before
their next session.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_duration_minutes(session_start_time: str | None) -> int:
    """Return elapsed minutes since session start, or 0 if unavailable."""
    if not session_start_time:
        return 0
    try:
        start = datetime.fromisoformat(session_start_time)
        # Ensure timezone-aware comparison
        now = datetime.now(timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        delta = now - start
        return max(0, int(delta.total_seconds() / 60))
    except (ValueError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Public agent entry point
# ---------------------------------------------------------------------------

async def run_reporting_agent(state: JobHunterState) -> dict:
    """Aggregate all session data into a :class:`SessionSummary`.

    Returns
    -------
    dict
        Keys: session_summary, status, agent_statuses, errors
    """
    errors: List[str] = []

    session_id: str = state.get("session_id", "unknown")

    try:
        await emit_agent_event(session_id, "reporting_progress", {
            "step": "Gathering session metrics...",
            "progress": 0,
        })

        # --- Gather raw numbers ---
        discovered_jobs = state.get("discovered_jobs", [])
        scored_jobs: List[ScoredJob] = state.get("scored_jobs", [])
        submitted: List[ApplicationResult] = state.get("applications_submitted", [])
        failed: List[ApplicationResult] = state.get("applications_failed", [])
        skipped: List[str] = state.get("applications_skipped", [])

        total_discovered = len(discovered_jobs)
        total_scored = len(scored_jobs)
        total_applied = len(submitted)
        total_failed = len(failed)
        total_skipped = len(skipped)

        # --- Top companies from submitted applications ---
        top_companies: List[str] = []
        # Build a lookup from job_id -> company via scored_jobs
        job_company_map = {sj.job.id: sj.job.company for sj in scored_jobs}
        seen_companies: set[str] = set()
        for app in submitted:
            company = job_company_map.get(app.job_id, "Unknown")
            if company not in seen_companies:
                seen_companies.add(company)
                top_companies.append(company)

        # --- Average fit score ---
        resume_scores = state.get("resume_scores", {})
        if resume_scores:
            avg_fit_score = round(
                sum(resume_scores.values()) / len(resume_scores), 1
            )
        elif scored_jobs:
            avg_fit_score = round(
                sum(sj.score for sj in scored_jobs) / len(scored_jobs), 1
            )
        else:
            avg_fit_score = 0.0

        # --- Duration ---
        duration_minutes = _compute_duration_minutes(
            state.get("session_start_time")
        )

        # --- AI-generated next steps ---
        await emit_agent_event(session_id, "reporting_progress", {
            "step": "Generating personalized next steps...",
            "progress": 50,
        })

        next_steps: List[str] = []
        try:
            llm = _build_llm()

            session_context = (
                f"Session summary:\n"
                f"- Jobs discovered: {total_discovered}\n"
                f"- Jobs scored: {total_scored}\n"
                f"- Applications submitted: {total_applied}\n"
                f"- Applications failed: {total_failed}\n"
                f"- Applications skipped: {total_skipped}\n"
                f"- Top companies: {', '.join(top_companies) or 'None'}\n"
                f"- Average fit score: {avg_fit_score}\n"
                f"- Session duration: {duration_minutes} minutes\n"
            )

            structured_llm = llm.with_structured_output(NextStepsResult)
            messages = [
                SystemMessage(content=NEXT_STEPS_SYSTEM),
                HumanMessage(content=session_context),
            ]
            result: NextStepsResult = await structured_llm.ainvoke(messages)
            next_steps = result.next_steps

        except Exception as exc:
            logger.warning("Failed to generate AI next steps: %s", exc)
            errors.append(f"Next-steps generation warning: {exc}")
            next_steps = [
                "Review submitted applications and follow up after 1 week.",
                "Refine resume keywords based on fit-score feedback.",
                "Expand search to additional job boards or locations.",
            ]

        # --- Build summary ---
        coach_output = state.get("coach_output")
        resume_score = coach_output.resume_score if coach_output else None

        summary = SessionSummary(
            session_id=session_id,
            total_discovered=total_discovered,
            total_scored=total_scored,
            total_applied=total_applied,
            total_failed=total_failed,
            total_skipped=total_skipped,
            top_companies=top_companies,
            avg_fit_score=avg_fit_score,
            resume_score=resume_score,
            duration_minutes=duration_minutes,
            next_steps=next_steps,
        )

        await emit_agent_event(session_id, "reporting_progress", {
            "step": f"Report ready: {total_applied} applied, avg fit {avg_fit_score}",
            "progress": 100,
        })

        logger.info(
            "Reporting complete: %d discovered, %d applied, avg fit %.1f",
            total_discovered,
            total_applied,
            avg_fit_score,
        )

        agent_status = (
            f"completed -- {total_applied} applied, "
            f"avg fit {avg_fit_score}, {duration_minutes}m elapsed"
        )

    except Exception as exc:
        logger.exception("Reporting agent failed")
        errors.append(f"Reporting agent error: {exc}")
        return {
            "session_summary": None,
            "status": "failed",
            "agent_statuses": {"reporting": f"failed -- {exc}"},
            "errors": errors,
        }

    return {
        "session_summary": summary,
        "status": "completed",
        "agent_statuses": {"reporting": agent_status},
        "errors": errors,
    }


# Alias for graph.py compatibility
run = run_reporting_agent
