"""Browser-Use Discovery -- LLM-driven job board scraping via browser-use.

Replaces hardcoded CSS selectors with an AI agent that dynamically
navigates job boards, searches keywords, and extracts listings.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from pydantic import BaseModel, Field

from backend.shared.config import get_settings
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import (
    ATSType,
    JobBoard,
    JobListing,
    SearchConfig,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured output models for browser-use
# ---------------------------------------------------------------------------

class DiscoveredJobRaw(BaseModel):
    """A single job extracted by the browser-use agent."""
    title: str
    company: str
    url: str
    location: str = "Unknown"
    salary_range: Optional[str] = None
    description_snippet: Optional[str] = None
    posted_date: Optional[str] = None
    is_remote: bool = False
    is_easy_apply: bool = False


class DiscoveredJobsOutput(BaseModel):
    """Structured output returned by the discovery agent."""
    jobs: List[DiscoveredJobRaw] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Board-specific prompt templates
# ---------------------------------------------------------------------------

_BOARD_PROMPTS: Dict[str, str] = {
    "indeed": """\
You are a job discovery agent. Search Indeed for job listings.

SEARCH PARAMETERS:
- Keywords (search one at a time): {keywords}
- Location: {location}
- Remote only: {remote_only}
- Minimum salary: {salary_min}

INSTRUCTIONS:
1. Go to https://www.indeed.com
2. For EACH keyword above:
   a. Enter the keyword in the "What" / job title search field
   b. Enter the location in the "Where" field (or leave blank if remote only)
   c. Click Search or press Enter
   d. If remote only, look for and click a "Remote" filter
   e. Extract up to {per_keyword} job listings from the search results
   f. For each listing card, extract: title, company name, location, the job URL (href from the listing link), salary range (if shown), a brief description snippet, posted date, whether it says "Remote", whether it has "Easily apply" badge
   g. If you need more results, click "Next" (max 2 pages per keyword)
3. After all keywords, report your findings.

RULES:
- Extract the ACTUAL job URL from each listing's link (href attribute), not the search page URL
- Do NOT click into individual job listings -- extract from the search result cards only
- If you see a CAPTCHA or block page, stop and report what you found so far
- Maximum {max_results} total listings across all keywords
""",

    "linkedin": """\
You are a job discovery agent. Search LinkedIn Jobs for listings.

SEARCH PARAMETERS:
- Keywords (search one at a time): {keywords}
- Location: {location}
- Remote only: {remote_only}

INSTRUCTIONS:
1. Go to https://www.linkedin.com/jobs/search
2. For EACH keyword above:
   a. Enter the keyword in the search/keywords field
   b. Enter the location (or skip if remote only)
   c. Submit the search
   d. If remote only, apply the "Remote" work type filter
   e. Extract up to {per_keyword} job listings from the results
   f. For each listing, extract: title, company name, location, job URL (should contain /jobs/view/), posted date, whether remote, whether "Easy Apply" badge is present
   g. Scroll down to load more results if needed (max 2 pages per keyword)
3. After all keywords, report findings.

RULES:
- Extract the actual job posting URL from each listing link
- If you hit a login wall or "Sign in" page, stop and report what you found
- LinkedIn rarely shows salary on cards -- leave salary_range empty if not visible
- Do NOT click into individual listings -- extract from search result cards only
- Maximum {max_results} total listings
""",

    "glassdoor": """\
You are a job discovery agent. Search Glassdoor for job listings.

SEARCH PARAMETERS:
- Keywords (search one at a time): {keywords}
- Location: {location}
- Remote only: {remote_only}
- Minimum salary: {salary_min}

INSTRUCTIONS:
1. Go to https://www.glassdoor.com/Job/jobs.htm
2. For EACH keyword above:
   a. Enter the keyword in the search field
   b. Enter the location
   c. Search
   d. If remote only, apply the remote filter
   e. Extract up to {per_keyword} listings
   f. For each listing, extract: title, company name, location, job URL, salary range (Glassdoor often shows salary estimates), description snippet, posted date, whether remote
   g. Click next page if needed (max 2 pages per keyword)
3. After all keywords, report findings.

RULES:
- Extract the actual job URL from each listing link
- If you see a login modal, try to close/dismiss it and continue
- If blocked by CAPTCHA, stop and report partial results
- Maximum {max_results} total listings
""",

    "ziprecruiter": """\
You are a job discovery agent. Search ZipRecruiter for job listings.

SEARCH PARAMETERS:
- Keywords (search one at a time): {keywords}
- Location: {location}
- Remote only: {remote_only}
- Minimum salary: {salary_min}

INSTRUCTIONS:
1. Go to https://www.ziprecruiter.com/jobs-search
2. For EACH keyword above:
   a. Enter the keyword in the search field
   b. Enter the location
   c. Search
   d. If remote only, apply remote/work-from-home filter
   e. Extract up to {per_keyword} listings
   f. For each listing, extract: title, company name, location, job URL, salary range (if shown), description snippet, posted date, whether remote, whether "1-Click Apply" or "Quick Apply" badge
   g. Click next page if needed (max 2 pages per keyword)
3. After all keywords, report findings.

RULES:
- Extract the actual job URL from each listing
- If you see a signup popup, dismiss it and continue
- If blocked, stop and report partial results
- Maximum {max_results} total listings
""",
}

PER_KEYWORD_DEFAULT = 8


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_discovery_prompt(
    board: str,
    search_config: SearchConfig,
    max_results: int,
) -> str:
    """Fill the board-specific prompt template with search parameters."""
    template = _BOARD_PROMPTS.get(board)
    if not template:
        raise ValueError(f"No discovery prompt for board: {board}")

    keywords = ", ".join(f'"{kw}"' for kw in search_config.keywords) if search_config.keywords else '"software engineer"'
    location = ", ".join(search_config.locations) if search_config.locations else "United States"
    if search_config.remote_only:
        location = "Remote"

    per_keyword = min(PER_KEYWORD_DEFAULT, max_results)

    return template.format(
        keywords=keywords,
        location=location,
        remote_only="Yes" if search_config.remote_only else "No",
        salary_min=f"${search_config.salary_min:,}" if search_config.salary_min else "any",
        per_keyword=per_keyword,
        max_results=max_results,
    )


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

async def _validate_urls(jobs: List[JobListing]) -> List[JobListing]:
    """Filter out jobs with dead URLs via async HEAD requests."""
    if not jobs:
        return jobs

    valid: List[JobListing] = []
    timeout = aiohttp.ClientTimeout(total=8)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async def _check(job: JobListing) -> Optional[JobListing]:
            try:
                async with session.head(
                    job.url,
                    allow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0"},
                ) as resp:
                    if resp.status < 400:
                        return job
                    logger.debug("URL validation failed (%d): %s", resp.status, job.url)
                    return None
            except Exception:
                # Network error or timeout -- keep the job (benefit of the doubt)
                return job

        results = await asyncio.gather(*[_check(j) for j in jobs])
        valid = [j for j in results if j is not None]

    dropped = len(jobs) - len(valid)
    if dropped:
        logger.info("URL validation dropped %d/%d jobs with dead links", dropped, len(jobs))

    return valid


# ---------------------------------------------------------------------------
# Core discovery function
# ---------------------------------------------------------------------------

async def discover_board(
    board: JobBoard,
    search_config: SearchConfig,
    session_id: str,
    max_results: int = 20,
) -> List[JobListing]:
    """Discover job listings on a single board using browser-use.

    Creates its own BrowserSession, runs the agent, validates URLs,
    and returns a list of JobListing objects.
    """
    from browser_use import Agent, Browser, ChatAnthropic

    settings = get_settings()
    board_name = board.value
    board_label = board_name.replace("_", " ").title()

    task = _build_discovery_prompt(board_name, search_config, max_results)

    llm = ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=8192,
        temperature=0.0,
    )

    browser = Browser(headless=False, disable_security=True)

    # SSE progress callback
    step_count = 0

    async def on_step_end(agent_instance):
        nonlocal step_count
        step_count += 1
        try:
            actions = agent_instance.history.model_actions()
            latest = str(actions[-1])[:200] if actions else "searching..."
            await emit_agent_event(session_id, "discovery_progress", {
                "board": board_name,
                "step": f"[{board_label}] Step {step_count}: {latest}",
            })
        except Exception:
            pass

    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        max_actions_per_step=5,
        use_vision=True,
        max_failures=3,
        output_model_schema=DiscoveredJobsOutput,
    )

    try:
        await emit_agent_event(session_id, "discovery_progress", {
            "board": board_name,
            "step": f"Searching {board_label} for jobs...",
        })

        result = await agent.run(max_steps=25, on_step_end=on_step_end)

        # Extract structured output
        raw_jobs: List[DiscoveredJobRaw] = []
        try:
            structured = result.final_result()
            if structured and isinstance(structured, str):
                # Try parsing as JSON
                import json
                parsed = json.loads(structured)
                if isinstance(parsed, dict) and "jobs" in parsed:
                    raw_jobs = [DiscoveredJobRaw(**j) for j in parsed["jobs"]]
                elif isinstance(parsed, list):
                    raw_jobs = [DiscoveredJobRaw(**j) for j in parsed]
        except Exception:
            logger.debug("Structured output parsing failed for %s, trying raw extraction", board_name, exc_info=True)

        if not raw_jobs:
            # Fallback: try to extract from the final result text
            final_text = str(result.final_result() or "")
            logger.warning(
                "No structured jobs from %s agent (steps=%d). Final: %s",
                board_name, step_count, final_text[:300],
            )

        # Convert to JobListing objects
        now = datetime.now(timezone.utc)
        listings: List[JobListing] = []
        for raw in raw_jobs[:max_results]:
            if not raw.url or not raw.title or not raw.company:
                continue
            listings.append(JobListing(
                id=str(uuid.uuid4()),
                title=raw.title.strip(),
                company=raw.company.strip(),
                location=raw.location.strip(),
                url=raw.url.strip(),
                board=board,
                ats_type=ATSType.UNKNOWN,
                salary_range=raw.salary_range,
                description_snippet=raw.description_snippet,
                posted_date=raw.posted_date,
                is_remote=raw.is_remote or "remote" in raw.location.lower(),
                is_easy_apply=raw.is_easy_apply,
                discovered_at=now,
            ))

        logger.info(
            "browser-use discovered %d jobs on %s (steps=%d)",
            len(listings), board_name, step_count,
        )

        # Validate URLs
        listings = await _validate_urls(listings)

        await emit_agent_event(session_id, "discovery_progress", {
            "board": board_name,
            "step": f"Found {len(listings)} verified {'job' if len(listings) == 1 else 'jobs'} on {board_label}",
            "count": len(listings),
            "progress": 100,
        })

        return listings

    except Exception as exc:
        logger.exception("browser-use discovery failed for %s", board_name)
        await emit_agent_event(session_id, "discovery_progress", {
            "board": board_name,
            "step": f"{board_label} discovery failed: {exc}",
            "progress": 100,
        })
        return []

    finally:
        try:
            await browser.stop()
        except Exception:
            pass
