# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Reporting Agent -- aggregates session data into a final summary."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.llm import build_llm as _shared_build_llm, invoke_with_retry, HAIKU_MODEL
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import (
    ApplicationResult,
    ScoredJob,
    SessionSummary,
)

logger = logging.getLogger(__name__)


class NextStepsResult(BaseModel):
    next_steps: List[str] = Field(description="3-5 actionable next steps for the candidate")

def _build_llm():
    return _shared_build_llm(model=HAIKU_MODEL, max_tokens=1024, temperature=0.4)


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
            "step": "Crunching the numbers on your session...",
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
        # Filter out zero/falsy values from resume_scores
        nonzero_scores = [v for v in (resume_scores or {}).values() if v]
        if nonzero_scores:
            avg_fit_score = round(sum(nonzero_scores) / len(nonzero_scores), 1)
        elif scored_jobs:
            scores = []
            for sj in scored_jobs:
                s = sj.score if hasattr(sj, "score") else sj.get("score", 0) if isinstance(sj, dict) else 0
                if s:
                    scores.append(s)
            avg_fit_score = round(sum(scores) / len(scores), 1) if scores else 0.0
        else:
            avg_fit_score = 0.0

        # --- Duration ---
        duration_minutes = _compute_duration_minutes(
            state.get("session_start_time")
        )

        # --- AI-generated next steps ---
        await emit_agent_event(session_id, "reporting_progress", {
            "step": "Writing your personalized next steps...",
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
            result: NextStepsResult = await invoke_with_retry(structured_llm, messages)
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
            "step": f"Summary ready — {total_applied} {'application' if total_applied == 1 else 'applications'} submitted, average fit score {avg_fit_score}",
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

        # --- Record outcome for self-improvement loop ---
        try:
            from backend.shared.outcome_store import record_outcome, get_outcome_count

            # Build error category breakdown from failed applications
            error_cats: dict[str, int] = {}
            for app in failed:
                cat = getattr(app, "error_category", "unknown") or "unknown"
                error_cats[cat] = error_cats.get(cat, 0) + 1

            # Build per-failure detail records for the feedback loop
            failure_details: list[dict] = []
            for app in failed:
                job_id = getattr(app, "job_id", "unknown")
                job_info = job_company_map.get(job_id, "Unknown")
                detail = {
                    "job_id": job_id,
                    "company": job_info,
                    "error_message": getattr(app, "error_message", None),
                    "error_category": (
                        getattr(app, "error_category", None)
                        or "unknown"
                    ),
                    "screenshot_url": getattr(app, "screenshot_url", None),
                    "ats_type": getattr(app, "ats_type", None),
                    "duration_seconds": getattr(app, "duration_seconds", None),
                }
                failure_details.append(detail)
            # Include skipped-with-reason (job_expired, auth_required)
            for app in state.get("applications_skipped_results", []):
                if hasattr(app, "error_message"):
                    failure_details.append({
                        "job_id": getattr(app, "job_id", "unknown"),
                        "company": job_company_map.get(getattr(app, "job_id", ""), "Unknown"),
                        "error_message": app.error_message,
                        "error_category": (
                            getattr(app, "error_category", None)
                            or "unknown"
                        ),
                        "screenshot_url": getattr(app, "screenshot_url", None),
                        "ats_type": getattr(app, "ats_type", None),
                        "duration_seconds": getattr(app, "duration_seconds", None),
                    })

            # Build ATS breakdown
            ats_breakdown: dict[str, dict] = {}
            for app in submitted:
                ats = getattr(app, "ats_type", "unknown") or "unknown"
                ats_breakdown.setdefault(ats, {"submitted": 0, "failed": 0})
                ats_breakdown[ats]["submitted"] += 1
            for app in failed:
                ats = getattr(app, "ats_type", "unknown") or "unknown"
                ats_breakdown.setdefault(ats, {"submitted": 0, "failed": 0})
                ats_breakdown[ats]["failed"] += 1

            session_config = state.get("session_config", {})
            search_config = {}
            if hasattr(session_config, "model_dump"):
                search_config = session_config.model_dump()
            elif isinstance(session_config, dict):
                search_config = session_config

            record_outcome(session_id, {
                "discovery_count": total_discovered,
                "scored_count": total_scored,
                "submitted_count": total_applied,
                "failed_count": total_failed,
                "skipped_count": total_skipped,
                "avg_fit_score": avg_fit_score,
                "error_categories": error_cats,
                "ats_breakdown": ats_breakdown,
                "failure_details": failure_details,
                "search_config": search_config,
            })

            # Trigger optimization every N sessions (if enabled)
            from backend.shared.config import get_settings
            settings = get_settings()
            outcome_count = get_outcome_count()
            n = settings.EVOAGENTX_OPTIMIZE_EVERY_N
            if settings.EVOAGENTX_ENABLED and outcome_count > 0 and outcome_count % n == 0:
                logger.info("Triggering prompt optimization (session count: %d)", outcome_count)
                try:
                    import asyncio
                    from backend.optimization.evolve import run_all_optimizations
                    loop = asyncio.get_event_loop()
                    loop.run_in_executor(None, run_all_optimizations)
                except Exception:
                    logger.warning("Prompt optimization trigger failed", exc_info=True)

        except Exception:
            logger.warning("Failed to record session outcome", exc_info=True)

        # --- Refresh ATS strategies from application feedback loop ---
        try:
            from backend.optimization.application_feedback import refresh_all_strategies
            import asyncio
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, refresh_all_strategies)
            logger.info("Triggered ATS strategy refresh from application feedback")
        except Exception:
            logger.warning("ATS strategy refresh failed", exc_info=True)

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
