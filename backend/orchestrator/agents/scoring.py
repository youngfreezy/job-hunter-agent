# Copyright (c) 2026 V2 Software LLC. All rights reserved.

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
from backend.shared.prompt_registry import get_active_prompt

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
You are an expert career-matching engine. Given a candidate's resume, their
SEARCH KEYWORDS (the roles they are actively looking for), and a batch of job
listings, score each job on how well the candidate fits.

For EACH job, produce a score with breakdown and reasons.

Scoring guidelines:
- keyword_match: This is the MOST IMPORTANT dimension. Evaluate TWO things:
  1. JOB TITLE ALIGNMENT with the candidate's search keywords. If the job title
     is a fundamentally different role than what the candidate searched for
     (e.g. "Data Scientist" when searching for "Full Stack Engineer"), the
     keyword_match MUST be 30 or below regardless of skill overlap.
  2. Skills/technologies overlap between the job description and resume.
  Title alignment should account for ~60% of keyword_match, skills overlap ~40%.
- location_match: 100 for exact match or remote; 50 for same state; 20 for relocation needed.
- salary_match: 100 if within resume's implied range; 50 if salary not listed; lower if clearly mismatched.
- experience_match: 100 if years of experience align; lower for over/under-qualified.
- overall score should be a weighted average: keyword 40%, experience 30%, location 15%, salary 15%.
- reasons: exactly 2 short bullet points, each under 12 words.
- fit_summary: 2-3 sentences explaining why this candidate is a strong fit for the role, referencing specific skills, experiences, or qualifications from their resume that match the job requirements. Write in second person ("You have...", "Your experience in...").

CRITICAL: A job whose title does not match the candidate's search keywords should
score LOW overall (typically under 50), even if the candidate has transferable
skills. The candidate chose specific keywords for a reason — respect their intent.
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


_ENTRY_LEVEL_KEYWORDS = [
    "new grad", "new graduate", "entry level", "entry-level", "intern ", "internship",
]


def filter_by_experience_level(
    jobs: List[JobListing], experience_level: str | None
) -> List[JobListing]:
    """Remove entry-level jobs when candidate is senior/executive."""
    if experience_level not in ("senior", "executive"):
        return jobs
    return [
        j for j in jobs
        if not any(kw in j.title.lower() for kw in _ENTRY_LEVEL_KEYWORDS)
    ]


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

        # On backfill rounds, only score newly discovered jobs (not re-score old ones)
        if state.get("backfill_rounds", 0) > 0:
            already_scored_ids = {str(sj.job.id) for sj in (state.get("scored_jobs") or [])}
            before = len(discovered_jobs)
            discovered_jobs = [j for j in discovered_jobs if str(j.id) not in already_scored_ids]
            logger.info(
                "Backfill scoring: %d total discovered, %d already scored, %d new to score",
                before, len(already_scored_ids), len(discovered_jobs),
            )
            if not discovered_jobs:
                logger.warning("Backfill scoring: no new jobs to score")
                return {
                    "scored_jobs": list(state.get("scored_jobs") or []),
                    "agent_statuses": {"scoring": "done (backfill: no new jobs)"},
                    "status": "tailoring",
                }

        # Step 1: Deduplicate
        config = state.get("session_config")
        cfg = config if isinstance(config, dict) else (config.model_dump() if config else {})
        is_quick_apply = cfg.get("discovery_mode") == "manual_urls"

        # Quick Apply: skip dedup — user explicitly chose each URL (e.g. two
        # Workday jobs both hydrate as company='Unknown', title='' and would
        # collapse into one entry)
        unique_jobs = discovered_jobs if is_quick_apply else _deduplicate_jobs(discovered_jobs)

        # Step 1b: Filter out jobs the user already applied to or companies at rate limit
        # Quick Apply: skip this filter — user explicitly chose these URLs
        user_id = state.get("user_id", "")
        if user_id and not is_quick_apply:
            try:
                from backend.shared.application_store import get_previously_applied_urls, get_rate_limited_companies
                applied_urls = get_previously_applied_urls(user_id)
                blocked_companies = get_rate_limited_companies(user_id)
                from backend.shared.billing_store import get_blocked_companies
                blocked_companies = blocked_companies | get_blocked_companies(user_id)
                before_filter = len(unique_jobs)
                unique_jobs = [
                    j for j in unique_jobs
                    if j.url not in applied_urls
                    and j.company.lower().strip() not in blocked_companies
                ]
                excluded = before_filter - len(unique_jobs)
                if excluded:
                    logger.info(
                        "Cross-session filter: excluded %d jobs (applied URLs: %d, rate-limited companies: %s) for user %s",
                        excluded, len(applied_urls), blocked_companies or "none", user_id,
                    )
                    session_id_for_event = state.get("session_id", "")
                    if session_id_for_event:
                        await emit_agent_event(session_id_for_event, "scoring_progress", {
                            "step": f"Filtered out {excluded} jobs (already applied or company limit reached)",
                        })
            except Exception:
                logger.warning("Cross-session dedup failed", exc_info=True)

        # Step 1c: Filter out entry-level jobs when the candidate is senior/executive
        search_config = state.get("search_config")
        experience_level = (
            search_config.experience_level
            if search_config and hasattr(search_config, "experience_level")
            else (search_config or {}).get("experience_level")
        )
        before_exp = len(unique_jobs)
        unique_jobs = filter_by_experience_level(unique_jobs, experience_level)
        _exp_excluded = before_exp - len(unique_jobs)
        if _exp_excluded:
            logger.info(
                "Experience-level filter: excluded %d entry-level jobs for %s candidate",
                _exp_excluded, experience_level,
            )

        logger.info(
            "Scoring agent starting -- %d unique jobs to score",
            len(unique_jobs),
        )

        # Quick Apply: skip LLM scoring entirely — user chose these jobs, score=100
        if is_quick_apply:
            scored_jobs = [
                ScoredJob(job=j, score=100, reasons=["Quick Apply — user selected"], fit_summary="User-provided URL")
                for j in unique_jobs
            ]
            logger.info("Quick Apply — skipping LLM scoring, assigned score=100 to %d jobs", len(scored_jobs))
            session_id = state.get("session_id", "")
            if session_id:
                await emit_agent_event(session_id, "scoring_complete", {
                    "scored_count": len(scored_jobs),
                })
            return {
                "scored_jobs": scored_jobs,
                "status": "tailoring",
                "agent_statuses": {"scoring": f"done — {len(scored_jobs)} jobs (Quick Apply)"},
            }

        # Step 2: Batch
        batches = _batch(unique_jobs, SCORING_BATCH_SIZE)

        # Step 3: Score batches concurrently (up to CONCURRENCY parallel LLM calls)
        session_id = state.get("session_id", "")

        all_scores: List[dict] = []
        completed_batches = 0
        total_batches = len(batches)

        # Pre-create LLM + structured wrapper once (shared across all batches)
        config = state.get("session_config")
        ai_temp = 0.0
        if config:
            ai_temp = config.ai_temperature if hasattr(config, "ai_temperature") else (config.get("ai_temperature", 0.0) if isinstance(config, dict) else 0.0)
        llm = build_llm(
            model=DEFAULT_MODEL,
            max_tokens=MAX_SCORING_TOKENS,
            temperature=ai_temp,
            timeout=120,
        )
        structured_llm = llm.with_structured_output(ScoringBatchResult)

        # Inject Moltbook strategy patches + dream insights into scoring context (if available)
        _strategy_context = ""
        try:
            from backend.moltbook.strategies import get_strategy_patches
            _strategy_context = get_strategy_patches()
            if _strategy_context:
                logger.info("Injecting %d chars of Moltbook strategy context into scoring", len(_strategy_context))
        except Exception as _strat_exc:
            logger.debug("Moltbook strategy injection skipped: %s", _strat_exc)

        # Dream insights are already included in get_strategy_patches() output
        # via the Consolidated Insights section, so no separate injection needed

        # Extract search keywords for title-alignment scoring
        search_config = state.get("search_config")
        _search_keywords: List[str] = []
        if search_config:
            _search_keywords = (
                search_config.keywords
                if hasattr(search_config, "keywords")
                else (search_config.get("keywords", []) if isinstance(search_config, dict) else [])
            )

        async def _score_batch(batch_idx: int, batch_jobs: List[JobListing]) -> List[dict]:
            """Score a single batch via LLM."""

            jobs_text = _jobs_to_prompt_text(batch_jobs)
            keywords_section = ""
            if _search_keywords:
                keywords_section = (
                    f"## Candidate's Search Keywords\n\n"
                    f"The candidate is searching for: {', '.join(_search_keywords)}\n"
                    f"Jobs whose titles do not align with these keywords should receive "
                    f"a LOW keyword_match score (30 or below).\n\n"
                )
            experience_section = ""
            if experience_level:
                experience_section = (
                    f"## Candidate Experience Level\n\n"
                    f"The candidate is **{experience_level}-level** based on their resume.\n"
                )
                if experience_level in ("senior", "executive"):
                    experience_section += (
                        "Jobs targeted at entry-level, new grads, interns, or junior candidates "
                        "are a POOR fit. Score their experience_match at 10 or below and overall "
                        "score should reflect this mismatch (typically under 40).\n\n"
                    )
                elif experience_level == "entry":
                    experience_section += (
                        "Jobs requiring 5+ years of experience or senior/staff/principal titles "
                        "are a POOR fit. Score their experience_match at 20 or below.\n\n"
                    )
            blocklist_section = ""
            if user_id:
                try:
                    from backend.shared.billing_store import get_user_by_id
                    _user_data = get_user_by_id(user_id)
                    _blocked_list = _user_data.get("blocked_companies", []) if _user_data else []
                    if _blocked_list:
                        blocklist_section = (
                            f"## Blocked Companies\n\n"
                            f"The candidate has permanently blocked these companies: {', '.join(_blocked_list)}.\n"
                            f"Any jobs from these companies MUST receive an overall score of 0.\n\n"
                        )
                except Exception:
                    pass

            user_prompt = (
                f"## Candidate Resume\n\n{resume}\n\n"
                f"{keywords_section}"
                f"{experience_section}"
                f"{blocklist_section}"
                f"## Job Listings (batch {batch_idx + 1}/{total_batches})\n\n{jobs_text}\n\n"
            )
            if _strategy_context:
                user_prompt += f"\n{_strategy_context}\n\n"
            user_prompt += "Score each job."

            messages = [
                SystemMessage(content=get_active_prompt("scoring_system") or SCORING_SYSTEM_PROMPT),
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

        # ATS applicability boost: Lever/Ashby submit successfully (no reCAPTCHA).
        # Greenhouse/Workday are blocked by reCAPTCHA on headless browsers.
        # Apply a real score boost so submittable jobs rank higher.
        _ATS_SCORE_BOOST = {"lever": 10, "ashby": 8, "greenhouse": -5, "workday": -5}
        for sj in scored_jobs:
            ats = (sj.job.ats_type.value if hasattr(sj.job.ats_type, 'value') else str(sj.job.ats_type or '')).lower()
            boost = _ATS_SCORE_BOOST.get(ats, 0)
            if boost:
                sj.score = max(0, min(100, sj.score + boost))
        scored_jobs.sort(key=lambda sj: sj.score, reverse=True)

        # Step 4b: Per-company dedup — keep only the highest-scored job per company
        # to avoid wasting application queue slots on duplicate companies
        company_best: dict[str, ScoredJob] = {}
        for sj in scored_jobs:
            company_key = sj.job.company.lower().strip()
            if company_key not in company_best or sj.score > company_best[company_key].score:
                company_best[company_key] = sj
        before_company_dedup = len(scored_jobs)
        scored_jobs = sorted(company_best.values(), key=lambda sj: sj.score, reverse=True)
        if len(scored_jobs) < before_company_dedup:
            logger.info(
                "Per-company dedup: %d -> %d jobs (removed %d duplicate companies)",
                before_company_dedup, len(scored_jobs), before_company_dedup - len(scored_jobs),
            )

        # Apply scoring_strictness as a minimum score threshold
        # 0.0 = lenient (min 30), 0.5 = moderate (min 50), 1.0 = strict (min 70)
        # Quick Apply (manual_urls): skip filtering — user chose these jobs explicitly
        config = state.get("session_config")
        strictness = 0.5  # default
        if config:
            cfg = config if isinstance(config, dict) else config.model_dump()
            if cfg.get("discovery_mode") == "manual_urls":
                strictness = 0.0  # no filtering for Quick Apply
                logger.info("Quick Apply session — skipping score filtering")
            else:
                strictness = cfg.get("scoring_strictness", 0.5)
        min_score = int(30 + strictness * 40)  # maps 0.0->30, 0.5->50, 1.0->70
        before_filter = len(scored_jobs)
        scored_jobs = [sj for sj in scored_jobs if sj.score >= min_score]
        if len(scored_jobs) < before_filter:
            logger.info(
                "Scoring strictness %.1f filtered %d -> %d jobs (min_score=%d)",
                strictness, before_filter, len(scored_jobs), min_score,
            )

        # Cap to max_jobs from session config
        max_jobs = 20  # default
        if config:
            cfg = config if isinstance(config, dict) else config.model_dump()
            max_jobs = cfg.get("max_jobs", 20)
        if len(scored_jobs) > max_jobs:
            logger.info("Capping scored jobs from %d to %d (session config)", len(scored_jobs), max_jobs)
            scored_jobs = scored_jobs[:max_jobs]

        # On backfill rounds, merge new scores with previously scored jobs
        if state.get("backfill_rounds", 0) > 0:
            prev_scored = list(state.get("scored_jobs") or [])
            new_ids = {str(sj.job.id) for sj in scored_jobs}
            merged = [sj for sj in prev_scored if str(sj.job.id) not in new_ids] + scored_jobs
            merged.sort(key=lambda sj: sj.score, reverse=True)
            scored_jobs = merged
            logger.info(
                "Backfill scoring: merged %d previous + %d new = %d total scored jobs",
                len(prev_scored), len(new_ids), len(scored_jobs),
            )

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
