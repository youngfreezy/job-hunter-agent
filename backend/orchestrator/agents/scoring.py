"""Scoring Agent -- ranks discovered jobs by fit against the coached resume/profile.

Uses the configured chat model to evaluate each job listing against the user's
resume, producing a 0-100 score with a breakdown across multiple dimensions.
Jobs are batched conservatively to avoid structured-output truncation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.shared.llm import build_llm, default_model, invoke_with_retry
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import (
    JobListing,
    ScoredJob,
)

logger = logging.getLogger(__name__)


class ScoreBreakdown(BaseModel):
    keyword_match: int = Field(ge=0, le=100)
    location_match: int = Field(ge=0, le=100)
    salary_match: int = Field(ge=0, le=100)
    experience_match: int = Field(ge=0, le=100)


class JobScore(BaseModel):
    job_id: str
    score: int = Field(ge=0, le=100)
    score_breakdown: ScoreBreakdown
    reasons: List[str] = Field(default_factory=list)
    fit_summary: str = Field(default="", description="2-3 sentences explaining why the candidate is a good fit for this role based on their resume")


class ScoringBatchResult(BaseModel):
    scores: List[JobScore] = Field(description="Scoring results for each job in the batch")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = default_model()
SCORING_BATCH_SIZE = 5
CONCURRENCY = 4
MAX_SCORING_TOKENS = 2500
MAX_DESCRIPTION_CHARS = 320

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SCORING_SYSTEM_PROMPT = """\
You are an expert career-matching engine. Given a candidate's resume and a batch
of job listings, score each job on how well the candidate fits.

For EACH job, produce a score with breakdown and reasons.

Scoring guidelines:
- keyword_match: Count overlapping skills, technologies, and domain keywords.
- location_match: 100 for exact match or remote; 50 for same state; 20 for relocation needed.
- salary_match: 100 if within resume's implied range; 50 if salary not listed; lower if clearly mismatched.
- experience_match: 100 if years of experience align; lower for over/under-qualified.
- overall score should be a weighted average: keyword 40%, experience 30%, location 15%, salary 15%.
- reasons: exactly 2 short bullet points, each under 12 words.
- fit_summary: 2-3 sentences explaining why this candidate is a strong fit for the role, referencing specific skills, experiences, or qualifications from their resume that match the job requirements. Write in second person ("You have...", "Your experience in...").
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deduplicate_jobs(jobs: List[JobListing]) -> List[JobListing]:
    """Remove duplicate listings (same company + similar title across boards).

    Uses a normalized key of (lowercase company, lowercase title with common
    suffixes stripped) to detect duplicates. Keeps the first occurrence.
    """
    seen: dict[str, JobListing] = {}
    for job in jobs:
        norm_company = job.company.strip().lower()
        norm_title = (
            job.title.strip()
            .lower()
            .replace("sr.", "senior")
            .replace("jr.", "junior")
        )
        key = f"{norm_company}|{norm_title}"
        if key not in seen:
            seen[key] = job
    deduped = list(seen.values())
    if len(deduped) < len(jobs):
        logger.info(
            "Deduplication removed %d duplicates (%d -> %d)",
            len(jobs) - len(deduped),
            len(jobs),
            len(deduped),
        )
    return deduped


def _batch(items: list, size: int) -> list[list]:
    """Split a list into batches of the given size."""
    return [items[i : i + size] for i in range(0, len(items), size)]


def _jobs_to_prompt_text(jobs: List[JobListing]) -> str:
    """Serialise a batch of JobListings into a compact text block for the LLM."""
    entries = []
    for job in jobs:
        description = (job.description_snippet or "N/A").strip()
        if len(description) > MAX_DESCRIPTION_CHARS:
            description = description[:MAX_DESCRIPTION_CHARS].rstrip() + "..."
        entries.append(
            f"- ID: {job.id}\n"
            f"  Title: {job.title}\n"
            f"  Company: {job.company}\n"
            f"  Location: {job.location}\n"
            f"  Remote: {job.is_remote}\n"
            f"  Salary: {job.salary_range or 'Not listed'}\n"
            f"  Description: {description}\n"
        )
    return "\n".join(entries)


# ---------------------------------------------------------------------------
# Main agent
# ---------------------------------------------------------------------------

async def run_scoring_agent(state: Dict[str, Any]) -> dict:
    """Score and rank discovered jobs against the candidate's resume.

    Steps:
    1. Deduplicate jobs across boards.
    2. Batch jobs conservatively.
    3. Score each batch via structured output, splitting on length-limit errors.
    4. Merge results, sort by score descending.
    """
    try:
        discovered_jobs: List[JobListing] = state.get("discovered_jobs", [])
        if not discovered_jobs:
            logger.warning("Scoring agent received 0 discovered jobs")
            return {
                "scored_jobs": [],
                "agent_statuses": {"scoring": "done"},
                "status": "tailoring",
            }

        # Use coached resume if available; fall back to raw resume_text
        resume = state.get("coached_resume") or state.get("resume_text", "")
        if not resume:
            logger.warning("No resume available for scoring -- using empty string")

        # Step 1: Deduplicate
        unique_jobs = _deduplicate_jobs(discovered_jobs)

        logger.info(
            "Scoring agent starting -- %d unique jobs to score",
            len(unique_jobs),
        )

        # Step 2: Batch
        batches = _batch(unique_jobs, SCORING_BATCH_SIZE)

        # Step 3: Score batches concurrently (up to CONCURRENCY parallel LLM calls)
        session_id = state.get("session_id", "")

        all_scores: List[dict] = []
        completed_batches = 0
        total_batches = len(batches)

        # Pre-create LLM + structured wrapper once (shared across all batches)
        llm = build_llm(
            model=DEFAULT_MODEL,
            max_tokens=MAX_SCORING_TOKENS,
            temperature=0.0,
            timeout=120,
        )
        structured_llm = llm.with_structured_output(ScoringBatchResult)

        async def _score_batch(batch_idx: int, batch_jobs: List[JobListing]) -> List[dict]:
            """Score a single batch via LLM."""

            jobs_text = _jobs_to_prompt_text(batch_jobs)
            user_prompt = (
                f"## Candidate Resume\n\n{resume}\n\n"
                f"## Job Listings (batch {batch_idx + 1}/{total_batches})\n\n{jobs_text}\n\n"
                "Score each job."
            )

            messages = [
                SystemMessage(content=SCORING_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]
            # Retry up to 2 times if structured output returns invalid/empty data
            last_exc: Exception | None = None
            for _attempt in range(3):
                try:
                    result: ScoringBatchResult = await invoke_with_retry(structured_llm, messages)
                    if result and hasattr(result, "scores") and result.scores:
                        return [s.model_dump() for s in result.scores]
                    logger.warning("Scoring batch %d returned empty result, retrying...", batch_idx + 1)
                except Exception as e:
                    last_exc = e
                    if "length limit" in str(e).lower() and len(batch_jobs) > 1:
                        midpoint = max(1, len(batch_jobs) // 2)
                        logger.warning(
                            "Scoring batch %d exceeded token budget, splitting %d jobs into %d + %d",
                            batch_idx + 1,
                            len(batch_jobs),
                            midpoint,
                            len(batch_jobs) - midpoint,
                        )
                        left = await _score_batch(batch_idx, batch_jobs[:midpoint])
                        right = await _score_batch(batch_idx, batch_jobs[midpoint:])
                        return left + right
                    logger.warning("Scoring batch %d attempt %d failed: %s", batch_idx + 1, _attempt + 1, e)
            raise last_exc or ValueError("Scoring returned empty results after 3 attempts")

        # Process in concurrent waves of CONCURRENCY
        for wave_start in range(0, total_batches, CONCURRENCY):
            wave = list(enumerate(batches[wave_start:wave_start + CONCURRENCY], start=wave_start))

            wave_pct = int((wave_start / total_batches) * 100)
            await emit_agent_event(session_id, "scoring_progress", {
                "step": f"Analyzing job fit — batch {wave_start + 1} of {total_batches}...",
                "progress": wave_pct,
                "batch": wave_start + 1,
                "total_batches": total_batches,
            })

            results = await asyncio.gather(
                *[_score_batch(idx, batch_jobs) for idx, batch_jobs in wave],
                return_exceptions=True,
            )

            for (batch_idx, _), result in zip(wave, results):
                if isinstance(result, Exception):
                    logger.error("Scoring batch %d failed: %s", batch_idx + 1, result)
                else:
                    all_scores.extend(result)
                completed_batches += 1

            done_pct = int((completed_batches / total_batches) * 100)
            await emit_agent_event(session_id, "scoring_progress", {
                "step": f"Ranked {len(all_scores)} jobs so far...",
                "progress": done_pct,
                "scored_so_far": len(all_scores),
            })

        # Step 4: Build ScoredJob objects and sort
        # Map job_id -> JobListing for fast lookup
        job_map: Dict[str, JobListing] = {job.id: job for job in unique_jobs}

        scored_jobs: List[ScoredJob] = []
        for score_data in all_scores:
            job_id = score_data.get("job_id", "")
            job = job_map.get(job_id)
            if job is None:
                logger.warning("Score returned for unknown job_id=%s -- skipping", job_id)
                continue

            scored_jobs.append(
                ScoredJob(
                    job=job,
                    score=max(0, min(100, int(score_data.get("score", 0)))),
                    score_breakdown={
                        k: max(0, min(100, int(v)))
                        for k, v in score_data.get("score_breakdown", {}).items()
                    },
                    reasons=score_data.get("reasons", []),
                    fit_summary=score_data.get("fit_summary", ""),
                )
            )

        # Sort descending by score
        scored_jobs.sort(key=lambda sj: sj.score, reverse=True)

        # Cap to max_jobs from session config
        config = state.get("session_config")
        max_jobs = 20  # default
        if config:
            cfg = config if isinstance(config, dict) else config.model_dump()
            max_jobs = cfg.get("max_jobs", 20)
        if len(scored_jobs) > max_jobs:
            logger.info("Capping scored jobs from %d to %d (session config)", len(scored_jobs), max_jobs)
            scored_jobs = scored_jobs[:max_jobs]

        logger.info(
            "Scoring agent finished -- %d jobs scored, top score=%d",
            len(scored_jobs),
            scored_jobs[0].score if scored_jobs else 0,
        )

        return {
            "scored_jobs": scored_jobs,
            "agent_statuses": {"scoring": "done"},
            "status": "tailoring",
        }

    except Exception as e:
        logger.exception("Scoring agent failed")
        return {
            "errors": [f"scoring failed: {str(e)}"],
            "agent_statuses": {"scoring": "failed"},
        }


# Alias for graph.py compatibility
run = run_scoring_agent
