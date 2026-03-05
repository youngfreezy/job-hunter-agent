"""Scoring Agent -- ranks discovered jobs by fit against the coached resume/profile.

Uses Claude Sonnet (claude-sonnet-4-6) to evaluate each job listing against the
user's resume, producing a 0-100 score with a breakdown across multiple dimensions.
Jobs are batched in groups of 10 to manage token limits.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.shared.config import settings
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


class ScoringBatchResult(BaseModel):
    scores: List[JobScore] = Field(description="Scoring results for each job in the batch")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-6"
SCORING_BATCH_SIZE = 10

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
- reasons: 2-3 short bullet points explaining the score.
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
        entries.append(
            f"- ID: {job.id}\n"
            f"  Title: {job.title}\n"
            f"  Company: {job.company}\n"
            f"  Location: {job.location}\n"
            f"  Remote: {job.is_remote}\n"
            f"  Salary: {job.salary_range or 'Not listed'}\n"
            f"  Description: {job.description_snippet or 'N/A'}\n"
        )
    return "\n".join(entries)


# ---------------------------------------------------------------------------
# Main agent
# ---------------------------------------------------------------------------

async def run_scoring_agent(state: Dict[str, Any]) -> dict:
    """Score and rank discovered jobs against the candidate's resume.

    Steps:
    1. Deduplicate jobs across boards.
    2. Batch jobs in groups of 10.
    3. Call Claude Sonnet for each batch (JSON mode).
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

        # Step 3: Score each batch via LLM with structured output
        session_id = state.get("session_id", "")
        llm = ChatAnthropic(
            model=DEFAULT_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=4096,
            temperature=0.0,  # deterministic scoring
            timeout=120,
        )
        structured_llm = llm.with_structured_output(ScoringBatchResult)

        all_scores: List[dict] = []

        for batch_idx, batch_jobs in enumerate(batches):
            logger.info(
                "Scoring batch %d/%d (%d jobs)",
                batch_idx + 1,
                len(batches),
                len(batch_jobs),
            )

            batch_pct = int((batch_idx / len(batches)) * 100)
            await emit_agent_event(session_id, "scoring_progress", {
                "step": f"Scoring batch {batch_idx + 1} of {len(batches)} ({len(batch_jobs)} jobs)...",
                "progress": batch_pct,
                "batch": batch_idx + 1,
                "total_batches": len(batches),
            })

            jobs_text = _jobs_to_prompt_text(batch_jobs)

            user_prompt = (
                f"## Candidate Resume\n\n{resume}\n\n"
                f"## Job Listings (batch {batch_idx + 1}/{len(batches)})\n\n{jobs_text}\n\n"
                "Score each job."
            )

            result: ScoringBatchResult = await structured_llm.ainvoke(
                [
                    SystemMessage(content=SCORING_SYSTEM_PROMPT),
                    HumanMessage(content=user_prompt),
                ]
            )

            all_scores.extend(s.model_dump() for s in result.scores)

            done_pct = int(((batch_idx + 1) / len(batches)) * 100)
            await emit_agent_event(session_id, "scoring_progress", {
                "step": f"Scored {len(all_scores)} jobs so far...",
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
                )
            )

        # Sort descending by score
        scored_jobs.sort(key=lambda sj: sj.score, reverse=True)

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
