"""Resume Tailor Agent -- customises the coached resume per job listing.

Tailors resumes concurrently in batches of CONCURRENCY to avoid blocking
the event loop for too long with sequential LLM calls.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.config import MAX_APPLICATION_JOBS
from backend.shared.llm import (
    build_llm as _shared_build_llm,
    default_model,
    invoke_with_retry,
    premium_model,
)
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import ScoredJob, TailoredResume

logger = logging.getLogger(__name__)


class TailorResult(BaseModel):
    tailored_text: str = Field(description="Full tailored resume text")
    fit_score: int = Field(ge=0, le=100, description="Fit score 0-100")
    changes_made: List[str] = Field(default_factory=list, description="List of changes made")

# ---------------------------------------------------------------------------
# Model helpers
# ---------------------------------------------------------------------------

SONNET_MODEL = default_model()
OPUS_MODEL = premium_model()
MAX_SELF_REFLECTION_RETRIES = 1
FIT_SCORE_THRESHOLD = 70
CONCURRENCY = 10  # Max parallel LLM calls for tailoring


def _pick_model(is_top_tier: bool) -> str:
    """Return Opus for top-20% jobs, Sonnet for the rest."""
    return OPUS_MODEL if is_top_tier else SONNET_MODEL


def _build_llm(model: str):
    return _shared_build_llm(model=model, max_tokens=8192, temperature=0.3)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

TAILOR_SYSTEM = """\
You are an expert resume writer. Given a base resume and a job description,
rewrite the resume so it is maximally relevant to this specific role while
remaining truthful. Emphasise matching keywords, transferable skills, and
quantified achievements.
"""

IMPROVE_SYSTEM = """\
You are an expert resume writer performing a second pass. The first tailored
resume scored below the quality bar. Improve it by addressing the specific
feedback below. Keep all facts truthful.
"""


# ---------------------------------------------------------------------------
# Core tailoring logic
# ---------------------------------------------------------------------------

async def _tailor_single(
    llm: BaseChatModel,
    base_resume: str,
    job: ScoredJob,
    allow_reflection: bool = True,
) -> TailoredResume:
    """Tailor a resume for a single job, with optional self-reflection retry.

    Self-reflection is only enabled for top-tier jobs (allow_reflection=True)
    to avoid doubling LLM calls on lower-priority resumes.
    """

    user_content = (
        f"## Base Resume\n{base_resume}\n\n"
        f"## Job Title\n{job.job.title} at {job.job.company}\n\n"
        f"## Job Description\n{job.job.description_snippet or 'N/A'}\n\n"
        f"## Job URL\n{job.job.url}\n"
    )

    structured_llm = llm.with_structured_output(TailorResult)

    messages = [
        SystemMessage(content=TAILOR_SYSTEM),
        HumanMessage(content=user_content),
    ]
    result: TailorResult = await invoke_with_retry(structured_llm, messages)

    fit_score = result.fit_score
    tailored_text = result.tailored_text
    changes_made = result.changes_made

    # --- Self-reflection loop (max 1 retry, top-tier jobs only) ---
    if allow_reflection and fit_score < FIT_SCORE_THRESHOLD:
        logger.info(
            "Fit score %d < %d for %s -- retrying with improvement instructions",
            fit_score,
            FIT_SCORE_THRESHOLD,
            job.job.id,
        )
        improve_content = (
            f"## Previous Tailored Resume\n{tailored_text}\n\n"
            f"## Previous Fit Score\n{fit_score}\n\n"
            f"## Job Title\n{job.job.title} at {job.job.company}\n\n"
            f"## Job Description\n{job.job.description_snippet or 'N/A'}\n\n"
            f"## Improvement Instructions\n"
            f"The fit score was {fit_score}/100.  Specifically:\n"
            f"- Increase keyword alignment with the job description.\n"
            f"- Strengthen quantified impact metrics.\n"
            f"- Improve ATS-friendly formatting.\n"
        )
        retry_messages = [
            SystemMessage(content=IMPROVE_SYSTEM),
            HumanMessage(content=improve_content),
        ]
        retry_result: TailorResult = await invoke_with_retry(structured_llm, retry_messages)
        fit_score = retry_result.fit_score
        tailored_text = retry_result.tailored_text
        changes_made = retry_result.changes_made

    return TailoredResume(
        job_id=job.job.id,
        original_text=base_resume,
        tailored_text=tailored_text,
        fit_score=fit_score,
        changes_made=changes_made,
    )


# ---------------------------------------------------------------------------
# Public agent entry point
# ---------------------------------------------------------------------------

async def run_resume_tailor_agent(state: JobHunterState) -> dict:
    """Tailor the coached resume for each job in the application queue.

    Uses the configured premium model for the top-20 % of scored jobs and the
    configured default model for the rest.

    Returns
    -------
    dict
        Keys: tailored_resumes, resume_scores, status, agent_statuses, errors
    """
    errors: List[str] = []
    tailored_resumes: Dict[str, TailoredResume] = {}
    resume_scores: Dict[str, int] = {}

    try:
        # Determine the base resume to tailor
        base_resume = state.get("coached_resume") or state.get("resume_text", "")
        if not base_resume:
            return {
                "tailored_resumes": {},
                "resume_scores": {},
                "status": "failed",
                "agent_statuses": {"resume_tailor": "failed -- no resume provided"},
                "errors": ["No resume text or coached resume available to tailor."],
            }

        scored_jobs: List[ScoredJob] = state.get("scored_jobs", [])
        if not scored_jobs:
            return {
                "tailored_resumes": {},
                "resume_scores": {},
                "status": "tailoring",
                "agent_statuses": {"resume_tailor": "completed -- no jobs to tailor"},
                "errors": [],
            }

        # Determine which jobs to tailor
        application_queue: List[str] = state.get("application_queue", [])
        if application_queue:
            jobs_to_tailor = [
                sj for sj in scored_jobs if sj.job.id in application_queue
            ]
        else:
            jobs_to_tailor = sorted(
                scored_jobs, key=lambda sj: sj.score, reverse=True
            )[:MAX_APPLICATION_JOBS]

        if not jobs_to_tailor:
            return {
                "tailored_resumes": {},
                "resume_scores": {},
                "status": "tailoring",
                "agent_statuses": {"resume_tailor": "completed -- empty queue"},
                "errors": [],
            }

        # Compute the top-20 % score threshold for model selection
        sorted_scores = sorted((sj.score for sj in jobs_to_tailor), reverse=True)
        top_20_index = max(1, len(sorted_scores) // 5) - 1
        top_20_threshold = sorted_scores[top_20_index]

        logger.info(
            "Tailoring %d resumes (top-20%% threshold score: %d)",
            len(jobs_to_tailor),
            top_20_threshold,
        )

        session_id = state.get("session_id", "")
        total_jobs = len(jobs_to_tailor)
        completed_count = 0

        # Pre-create LLM instances (one per model) to avoid per-job overhead
        sonnet_llm = _build_llm(SONNET_MODEL)
        opus_llm = _build_llm(OPUS_MODEL)

        # Process in concurrent batches to avoid blocking the event loop
        for batch_start in range(0, total_jobs, CONCURRENCY):
            batch = jobs_to_tailor[batch_start:batch_start + CONCURRENCY]

            pct = int((batch_start / total_jobs) * 100)
            await emit_agent_event(session_id, "tailoring_progress", {
                "step": f"Customizing resume {batch_start + 1} of {total_jobs}...",
                "progress": pct,
                "current": batch_start + 1,
                "total": total_jobs,
            })

            async def _tailor_one(sj: ScoredJob) -> tuple:
                """Tailor a single job, return (job_id, result_or_error)."""
                try:
                    is_top_tier = sj.score >= top_20_threshold
                    llm = opus_llm if is_top_tier else sonnet_llm
                    model_name = OPUS_MODEL if is_top_tier else SONNET_MODEL
                    logger.info("Tailoring for %s (%s) using %s", sj.job.id, sj.job.title, model_name)
                    tailored = await _tailor_single(llm, base_resume, sj, allow_reflection=is_top_tier)
                    return (sj.job.id, tailored, None)
                except Exception as exc:
                    return (sj.job.id, None, exc)

            results = await asyncio.gather(*[_tailor_one(sj) for sj in batch])

            for job_id, tailored, exc in results:
                if tailored:
                    tailored_resumes[job_id] = tailored
                    resume_scores[job_id] = tailored.fit_score
                    completed_count += 1
                else:
                    error_msg = f"Failed to tailor resume for job {job_id}: {exc}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            done_pct = int(((batch_start + len(batch)) / total_jobs) * 100)
            await emit_agent_event(session_id, "tailoring_progress", {
                "step": f"Customized {completed_count} of {total_jobs} resumes",
                "progress": done_pct,
                "current": batch_start + len(batch),
                "total": total_jobs,
            })

        status = "tailoring"
        agent_status = (
            f"completed -- tailored {len(tailored_resumes)}/{len(jobs_to_tailor)} resumes"
        )
        if errors:
            agent_status += f" ({len(errors)} errors)"

    except Exception as exc:
        logger.exception("Resume tailor agent failed")
        errors.append(f"Resume tailor agent error: {exc}")
        status = "failed"
        agent_status = f"failed -- {exc}"

    return {
        "tailored_resumes": tailored_resumes,
        "resume_scores": resume_scores,
        "status": status,
        "agent_statuses": {"resume_tailor": agent_status},
        "errors": errors,
    }


# Alias for graph.py compatibility
run = run_resume_tailor_agent
