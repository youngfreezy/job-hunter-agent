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

    import json
    import logging
    from backend.shared.llm import build_llm, invoke_with_retry, HAIKU_MODEL

    logger = logging.getLogger(__name__)

    # Build a compact list for the LLM
    job_summaries = []
    for i, job in enumerate(listings):
        job_summaries.append({
            "idx": i,
            "title": job.title,
            "company": job.company,
            "location": job.location or "",
        })

    prompt = f"""You are a job relevance ranker. Given these search keywords and job listings, return the indices of the {limit} most relevant jobs, ranked best first.

Keywords: {', '.join(keywords)}

Jobs:
{json.dumps(job_summaries, indent=1)}

Return ONLY a JSON array of the top {limit} indices, e.g. [3, 0, 7, 1, 5]. No explanation."""

    try:
        llm = build_llm(model=HAIKU_MODEL, max_tokens=256, temperature=0.0)
        response = await invoke_with_retry(llm, [("human", prompt)], max_retries=2)
        text = response.content.strip()

        # Parse the JSON array from response
        if "[" in text:
            text = text[text.index("["):text.rindex("]") + 1]
        indices = json.loads(text)
        ranked = []
        seen = set()
        for idx in indices:
            if isinstance(idx, int) and 0 <= idx < len(listings) and idx not in seen:
                ranked.append(listings[idx])
                seen.add(idx)
        if ranked:
            logger.info("LLM ranked %d/%d listings for top %d", len(ranked), len(listings), limit)
            return ranked[:limit]
    except Exception:
        logger.warning("LLM ranking failed, falling back to keyword match", exc_info=True)

    # Fallback: simple keyword-match scoring
    lower_keywords = [kw.lower() for kw in keywords]

    def _score(job: JobListing) -> int:
        text = " ".join(filter(None, [
            job.title, job.company, job.location, job.description_snippet,
        ])).lower()
        return sum(1 for kw in lower_keywords if kw in text)

    ranked = sorted(listings, key=_score, reverse=True)
    return ranked[:limit]
