"""Job board scrapers for Indeed, LinkedIn, Glassdoor, and Google Jobs.

Each scraper follows the same interface::

    async def scrape_<board>(
        context: BrowserContext,
        search_config: SearchConfig,
        *,
        max_results: int = ...,
    ) -> list[JobListing]

The *context* should be an isolated Playwright BrowserContext obtained from
:class:`~backend.browser.manager.BrowserManager`.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from backend.browser.tools.job_boards.glassdoor import scrape_glassdoor
from backend.browser.tools.job_boards.google_jobs import scrape_google_jobs
from backend.browser.tools.job_boards.indeed import scrape_indeed
from backend.browser.tools.job_boards.linkedin import scrape_linkedin
from backend.browser.tools.job_boards.ziprecruiter import scrape_ziprecruiter
from backend.shared.models.schemas import JobListing

__all__ = [
    "rank_by_relevance",
    "scrape_glassdoor",
    "scrape_google_jobs",
    "scrape_indeed",
    "scrape_linkedin",
    "scrape_ziprecruiter",
]


class RankedListingIndices(BaseModel):
    """Structured ranking response from the LLM."""

    indices: List[int] = Field(default_factory=list)


RANKING_CHUNK_SIZE = 15
RANKING_MAX_TOKENS = 400


def _keyword_score(job: JobListing, keywords: List[str]) -> int:
    text = " ".join(
        filter(
            None,
            [job.title, job.company, job.location, job.description_snippet],
        )
    ).lower()
    return sum(1 for kw in keywords if kw in text)


async def _rank_chunk(
    listings: List[JobListing],
    keywords: List[str],
    limit: int,
) -> List[JobListing]:
    import json
    import logging
    from backend.shared.llm import build_llm, invoke_with_retry, HAIKU_MODEL

    logger = logging.getLogger(__name__)

    job_summaries = []
    for i, job in enumerate(listings):
        job_summaries.append({
            "idx": i,
            "title": job.title,
            "company": job.company,
            "location": job.location or "",
        })

    prompt = f"""You are a job relevance ranker for a Senior AI Engineer. Rank these jobs by relevance to ALL of the search keywords, not just one.

IMPORTANT:
- Prefer jobs that match multiple keywords over generic title overlaps.
- Return exactly the strongest {limit} indices when possible.
- Keep the ordering best-first.

Keywords: {', '.join(keywords)}

Jobs:
{json.dumps(job_summaries, indent=1)}
"""

    llm = build_llm(model=HAIKU_MODEL, max_tokens=RANKING_MAX_TOKENS, temperature=0.0)
    structured_llm = llm.with_structured_output(RankedListingIndices)
    response = await invoke_with_retry(
        structured_llm,
        [("human", prompt)],
        max_retries=2,
    )

    ranked = []
    seen = set()
    for idx in response.indices:
        if isinstance(idx, int) and 0 <= idx < len(listings) and idx not in seen:
            ranked.append(listings[idx])
            seen.add(idx)

    if ranked:
        logger.info(
            "LLM ranked %d/%d listings for top %d",
            len(ranked),
            len(listings),
            limit,
        )
    return ranked[:limit]


async def rank_by_relevance(
    listings: List[JobListing],
    keywords: List[str],
    limit: int = 5,
) -> List[JobListing]:
    """Rank listings by relevance using an LLM and return the top *limit*.

    Uses Haiku for fast, cheap ranking. Falls back to keyword-match
    scoring if the LLM call fails.
    """
    if not listings:
        return []
    if len(listings) <= limit:
        return listings

    import logging

    logger = logging.getLogger(__name__)

    try:
        if len(listings) <= RANKING_CHUNK_SIZE:
            ranked = await _rank_chunk(listings, keywords, limit)
            if ranked:
                return ranked
        else:
            candidate_limit = min(
                RANKING_CHUNK_SIZE,
                max(limit * 2, 6),
            )
            candidates: List[JobListing] = []
            seen_ids: set[str] = set()
            for start in range(0, len(listings), RANKING_CHUNK_SIZE):
                chunk = listings[start : start + RANKING_CHUNK_SIZE]
                ranked_chunk = await _rank_chunk(
                    chunk,
                    keywords,
                    min(candidate_limit, len(chunk)),
                )
                for job in ranked_chunk:
                    if job.id not in seen_ids:
                        candidates.append(job)
                        seen_ids.add(job.id)

            if candidates:
                final_pool = candidates[: max(limit * 3, RANKING_CHUNK_SIZE)]
                ranked = await _rank_chunk(final_pool, keywords, min(limit, len(final_pool)))
                if ranked:
                    return ranked
    except Exception:
        logger.warning("LLM ranking failed, falling back to keyword match", exc_info=True)

    # Fallback: simple keyword-match scoring
    lower_keywords = [kw.lower() for kw in keywords]

    ranked = sorted(listings, key=lambda job: _keyword_score(job, lower_keywords), reverse=True)
    return ranked[:limit]
