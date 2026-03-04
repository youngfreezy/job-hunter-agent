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

from backend.shared.config import settings
from backend.shared.models.schemas import (
    JobListing,
    ScoredJob,
)

logger = logging.getLogger(__name__)

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

For EACH job produce a JSON object with:
- job_id (str): the id of the job listing
- score (int 0-100): overall fit score
- score_breakdown (object):
    - keyword_match (int 0-100): how well the job's required skills match the resume
    - location_match (int 0-100): 100 if location/remote preferences align, lower otherwise
    - salary_match (int 0-100): 100 if salary range aligns with experience level, 50 if unknown
    - experience_match (int 0-100): how well the candidate's experience level matches the role
- reasons (list[str]): 2-3 short bullet points explaining the score

Scoring guidelines:
- keyword_match: Count overlapping skills, technologies, and domain keywords.
- location_match: 100 for exact match or remote; 50 for same state; 20 for relocation needed.
- salary_match: 100 if within resume's implied range; 50 if salary not listed; lower if clearly mismatched.
- experience_match: 100 if years of experience align; lower for over/under-qualified.
- overall score should be a weighted average: keyword 40%, experience 30%, location 15%, salary 15%.

Return ONLY valid JSON -- an array of scoring objects. No markdown, no explanation.
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

        # Step 3: Score each batch via LLM (JSON mode for structured output)
        llm = ChatAnthropic(
            model=DEFAULT_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=4096,
            temperature=0.0,  # deterministic scoring
            model_kwargs={"response_format": {"type": "json_object"}},
        )

        all_scores: List[dict] = []

        for batch_idx, batch_jobs in enumerate(batches):
            logger.info(
                "Scoring batch %d/%d (%d jobs)",
                batch_idx + 1,
                len(batches),
                len(batch_jobs),
            )
            jobs_text = _jobs_to_prompt_text(batch_jobs)

            user_prompt = (
                f"## Candidate Resume\n\n{resume}\n\n"
                f"## Job Listings (batch {batch_idx + 1}/{len(batches)})\n\n{jobs_text}\n\n"
                "Score each job and return the JSON array."
            )

            response = await llm.ainvoke(
                [
                    SystemMessage(content=SCORING_SYSTEM_PROMPT),
                    HumanMessage(content=user_prompt),
                ]
            )

            raw_text = response.content
            if isinstance(raw_text, list):
                raw_text = "".join(
                    block if isinstance(block, str) else block.get("text", "")
                    for block in raw_text
                )

            parsed = json.loads(raw_text)
            # Handle both {"scores": [...]} and direct [...] responses
            if isinstance(parsed, dict):
                parsed = parsed.get("scores", parsed.get("results", []))
            all_scores.extend(parsed)

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
