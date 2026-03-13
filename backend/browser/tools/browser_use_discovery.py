"""Browser-Use Discovery -- single-agent, single-browser job discovery.

One browser-use agent navigates all job boards sequentially in a single
Chrome session. No per-board restarts, no competing resources.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from pydantic import BaseModel, Field

from backend.shared.event_bus import emit_agent_event
from backend.shared.llm import build_browser_use_llm
from backend.shared.selector_memory import get_top_selectors, record_success
from backend.shared.models.schemas import (
    ATSType,
    JobBoard,
    JobListing,
    SearchConfig,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured output models
# ---------------------------------------------------------------------------

class DiscoveredJobRaw(BaseModel):
    """A single job extracted by the browser-use agent."""
    title: str
    company: str
    url: str
    board: str = "unknown"
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
# Board URL map
# ---------------------------------------------------------------------------

_BOARD_URLS = {
    "linkedin": "https://www.linkedin.com/jobs/search",
    "ziprecruiter": "https://www.ziprecruiter.com/jobs-search",
    "indeed": "https://www.indeed.com",
    "glassdoor": "https://www.glassdoor.com/Job/jobs.htm",
}


# ---------------------------------------------------------------------------
# Prompt builder -- single unified task for all boards
# ---------------------------------------------------------------------------

# Fallback selectors if DB has no history yet
_DEFAULT_SELECTORS: Dict[str, str] = {
    "glassdoor": (
        "li[class*='JobsList'] > div, "
        "li[data-test], "
        "li.JobsList_jobListItem__JBBUV, "
        "li.react-job-listing"
    ),
}

def _get_board_selectors(board: str) -> Optional[str]:
    """Get known-working selectors for a board from DB, with fallback defaults."""
    db_selectors = get_top_selectors(board, limit=5)
    if db_selectors:
        return ", ".join(db_selectors)
    return _DEFAULT_SELECTORS.get(board)

def _build_unified_prompt(
    boards: List[str],
    search_config: SearchConfig,
    max_per_board: int,
) -> str:
    # Limit to top 4 keywords to keep steps manageable
    top_keywords = (search_config.keywords or ["software engineer"])[:4]
    keywords = ", ".join(f'"{kw}"' for kw in top_keywords)
    location = ", ".join(search_config.locations) if search_config.locations else "United States"
    if search_config.remote_only:
        location = "Remote"

    board_sections = []
    for i, board in enumerate(boards, 1):
        url = _BOARD_URLS.get(board, "")
        extra = ""
        known_selectors = _get_board_selectors(board)
        if known_selectors:
            extra += f"\n  - KNOWN WORKING selectors for {board}: {known_selectors}"
        if board == "glassdoor":
            extra += "\n  - Glassdoor is slow to load. If you wait more than twice, skip it."
        board_sections.append(
            f"BOARD {i}: {board.upper()} ({url})\n"
            f"  - Go to {url}\n"
            f"  - Search each keyword with location \"{location}\"\n"
            f"  - Extract up to {max_per_board} job listings from search result cards\n"
            f"  - For each job: title, company, job URL (from listing link href), location, salary (if shown), description snippet, posted date, remote status, easy-apply badge\n"
            f"  - If blocked/CAPTCHA/login-wall: stop this board and move to the next\n"
            f"  - Include board=\"{board}\" for each job from this site"
            f"{extra}"
        )

    return f"""\
You are a job discovery agent. Search multiple job boards for listings.

SEARCH PARAMETERS:
- Keywords: {keywords}
- Location: {location}

Search these boards IN ORDER, one at a time in the SAME browser tab:

{chr(10).join(board_sections)}

EXTRACTION STRATEGY (use this for every board):
1. Navigate to the board URL
2. Dismiss any popups/login walls (click X or press Escape)
3. Type a keyword in the search box and search
4. Use evaluate() with JavaScript to extract job data from the page DOM in ONE step. Example:
   evaluate(code="(() => {{ const cards = document.querySelectorAll('.job-card, .jobCard, [data-job-id], .job_seen_beacon, .jobs-search__results-list li'); return JSON.stringify(Array.from(cards).slice(0, 5).map(c => ({{ title: (c.querySelector('h2, h3, [class*=title], .job-title') || {{}}).textContent?.trim(), company: (c.querySelector('[class*=company], [class*=subtitle], .company') || {{}}).textContent?.trim(), url: (c.querySelector('a[href]') || {{}}).href, location: (c.querySelector('[class*=location]') || {{}}).textContent?.trim() }})).filter(j => j.title && j.url)); }})()")
5. Move to the next keyword or next board. Do NOT call find_elements repeatedly.

RULES:
- Do NOT click into individual listings -- extract from search result cards only
- Do NOT use the extract action or find_elements in a loop -- use evaluate() with JS to grab all data at once
- Do NOT click filters (salary, date, etc.) -- just extract whatever is on the search results page
- If a login wall or popup appears, close it (click X, dismiss, or press Escape) and continue extracting. Only skip the board if you literally cannot see any job listings after dismissing.
- If a board shows a CAPTCHA or hard block, skip it IMMEDIATELY and go to the next board. Do NOT retry failed navigations.
- STRICT STEP BUDGET: You have at most 8 steps per board. If you haven't extracted jobs in 8 steps, SKIP and move to the next board immediately. Do NOT waste steps waiting or retrying.
- If you find yourself waiting (wait action) more than twice in a row on a board, SKIP it and move to the next board.
- For each keyword, search and extract, then move to the next keyword. Do NOT search every keyword -- pick the top 2 most relevant.
- Maximum {max_per_board} listings per board
- Include the "board" field (indeed/linkedin/glassdoor/ziprecruiter) for each job
- Be FAST: navigate, search, evaluate() once to extract, move on.
- When done with ALL boards, call done with this EXACT JSON format:
  {{"jobs": [{{"title": "...", "company": "...", "url": "...", "board": "indeed", "location": "...", "salary_range": "..." or null, "description_snippet": "..." or null, "posted_date": "..." or null, "is_remote": true/false, "is_easy_apply": true/false}}]}}
"""


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
                return job  # benefit of the doubt

        results = await asyncio.gather(*[_check(j) for j in jobs])
        valid = [j for j in results if j is not None]

    dropped = len(jobs) - len(valid)
    if dropped:
        logger.info("URL validation dropped %d/%d jobs with dead links", dropped, len(jobs))

    return valid


# ---------------------------------------------------------------------------
# Board name -> JobBoard enum
# ---------------------------------------------------------------------------

_BOARD_MAP = {
    "indeed": JobBoard.INDEED,
    "linkedin": JobBoard.LINKEDIN,
    "glassdoor": JobBoard.GLASSDOOR,
    "ziprecruiter": JobBoard.ZIPRECRUITER,
}


# ---------------------------------------------------------------------------
# Human-readable step descriptions for SSE
# ---------------------------------------------------------------------------

def _friendly_step(action: Any, action_results: Any, *, board: str = "unknown", keyword: str = "") -> str:
    """Convert raw browser-use action into a short human-readable string."""
    if action is None:
        return "Searching..."
    act = action if isinstance(action, dict) else (action.__dict__ if hasattr(action, "__dict__") else {})
    # Navigate
    if "navigate" in act:
        url = act["navigate"].get("url", "") if isinstance(act["navigate"], dict) else str(act["navigate"])
        domain = url.split("//")[-1].split("/")[0] if "//" in url else url
        return f"Navigating to {domain}"
    # Click
    if "click" in act:
        if action_results:
            last = action_results[-1] if action_results else None
            items = last if isinstance(last, list) else [last]
            for r in items:
                text = str(r) if r else ""
                if "aria-label=" in text:
                    label = text.split("aria-label=")[1].split("'")[0].split('"')[0][:50]
                    return f"Clicked: {label}"
                if "extracted_content=" in text and "Clicked" in text:
                    snippet = text.split("extracted_content='")[1].split("'")[0][:60] if "extracted_content='" in text else ""
                    if snippet:
                        return snippet
        return "Clicking element on page"
    # Evaluate (JS extraction)
    if "evaluate" in act:
        if action_results:
            last = action_results[-1] if action_results else None
            items = last if isinstance(last, list) else [last]
            for r in items:
                mem = getattr(r, "long_term_memory", None) or (str(r) if r else "")
                mem_str = str(mem)
                if mem_str.startswith("[") and '"title"' in mem_str:
                    try:
                        count = len(json.loads(mem_str))
                        if count > 0:
                            parts = [f"Extracted {count} job listings"]
                            if keyword:
                                parts.append(f"with '{keyword}'")
                            if board and board != "unknown":
                                parts.append(f"on {board.title()}")
                            return " ".join(parts)
                    except Exception:
                        pass
        return "Extracting job listings from page"
    # Find elements
    if "find_elements" in act:
        return "Scanning page for job cards"
    # Input text
    if "input_text" in act:
        text = act["input_text"].get("text", "") if isinstance(act["input_text"], dict) else ""
        return f'Searching for "{text}"' if text else "Typing search query"
    # Done
    if "done" in act:
        return "Finished searching all boards"
    return "Processing..."


# ---------------------------------------------------------------------------
# Convert raw jobs to JobListing objects
# ---------------------------------------------------------------------------

def _raw_to_listings(raw_jobs: List[DiscoveredJobRaw]) -> List[JobListing]:
    """Convert DiscoveredJobRaw list to JobListing list."""
    now = datetime.now(timezone.utc)
    listings: List[JobListing] = []
    for raw in raw_jobs:
        if not raw.url or not raw.title or not raw.company:
            continue
        board_enum = _BOARD_MAP.get(raw.board.lower(), JobBoard.INDEED)
        listings.append(JobListing(
            id=str(uuid.uuid4()),
            title=raw.title.strip(),
            company=raw.company.strip(),
            location=raw.location.strip(),
            url=raw.url.strip(),
            board=board_enum,
            ats_type=ATSType.UNKNOWN,
            salary_range=raw.salary_range,
            description_snippet=raw.description_snippet,
            posted_date=raw.posted_date,
            is_remote=raw.is_remote or "remote" in raw.location.lower(),
            is_easy_apply=raw.is_easy_apply,
            discovered_at=now,
        ))
    return listings


# ---------------------------------------------------------------------------
# Core: single-agent discovery across all boards
# ---------------------------------------------------------------------------

async def discover_all_boards(
    boards: List[str],
    search_config: SearchConfig,
    session_id: str,
    max_per_board: int = 20,
) -> List[JobListing]:
    """Run one browser-use agent that searches all boards sequentially."""
    from browser_use import Agent, Browser

    # Reorder boards: reliable first, glassdoor last (heavy CDP timeouts)
    priority = ["linkedin", "ziprecruiter", "indeed", "glassdoor"]
    boards = sorted(boards, key=lambda b: priority.index(b) if b in priority else 99)

    task = _build_unified_prompt(boards, search_config, max_per_board)

    llm = build_browser_use_llm(max_tokens=8192, temperature=0.0)

    from backend.shared.config import settings

    browser = Browser(
        headless=settings.BROWSER_HEADLESS,
        disable_security=True,
        wait_for_network_idle_page_load_time=2.0,
    )

    step_count = 0
    current_board = "unknown"
    current_keyword = ""
    # Accumulate extracted jobs from evaluate() steps so data survives timeouts
    recovered_jobs: List[DiscoveredJobRaw] = []
    seen_urls: set = set()

    def _extract_selector_from_code(code: str) -> Optional[str]:
        """Extract the querySelectorAll argument from evaluate() JS code."""
        import re
        m = re.search(r"querySelectorAll\(['\"](.+?)['\"]\)", code)
        return m.group(1) if m else None

    def _try_recover_jobs(action_results: Any, last_action: Any = None) -> None:
        """Parse job JSON arrays from evaluate() results and accumulate them."""
        if not action_results:
            return
        last = action_results[-1] if action_results else None
        items = last if isinstance(last, list) else [last]
        new_count = 0
        for r in items:
            mem = getattr(r, "long_term_memory", None) or ""
            mem_str = str(mem)
            if '"title"' not in mem_str:
                continue
            try:
                parsed = json.loads(mem_str)
                # Handle both [{...}] and {"jobs": [{...}]} formats
                if isinstance(parsed, dict) and "jobs" in parsed:
                    parsed_list = parsed["jobs"]
                elif isinstance(parsed, list):
                    parsed_list = parsed
                else:
                    continue
                for j in parsed_list:
                    if not isinstance(j, dict):
                        continue
                    url = j.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    if not j.get("title") or not j.get("company"):
                        continue
                    if not j.get("board") or j["board"] == "unknown":
                        j["board"] = current_board
                    seen_urls.add(url)
                    try:
                        recovered_jobs.append(DiscoveredJobRaw(**j))
                        new_count += 1
                    except Exception:
                        pass
            except (json.JSONDecodeError, Exception):
                pass

        # Record successful selector to DB for future runs
        if new_count > 0 and last_action and current_board != "unknown":
            act = last_action if isinstance(last_action, dict) else (last_action.__dict__ if hasattr(last_action, "__dict__") else {})
            if "evaluate" in act:
                code = act["evaluate"].get("code", "") if isinstance(act["evaluate"], dict) else str(act["evaluate"])
                selector = _extract_selector_from_code(code)
                if selector:
                    record_success(current_board, selector)
                    logger.info("Recorded working selector for %s: %s", current_board, selector[:80])

    async def on_step_end(agent_instance):
        nonlocal step_count, current_board, current_keyword
        step_count += 1
        try:
            actions = agent_instance.history.model_actions()
            latest_raw = str(actions[-1])[:200] if actions else "searching..."
            # Log full detail to backend.log
            action_results = agent_instance.history.action_results()
            if action_results:
                last_results = action_results[-1] if action_results else []
                for r in (last_results if isinstance(last_results, list) else [last_results]):
                    text = str(r)[:500] if r else ""
                    if text and len(text) > 10:
                        logger.debug("  [result] len=%d", len(text))
            logger.info("Step %d: %s", step_count, latest_raw)

            # Track current board from navigate actions
            last_action = actions[-1] if actions else None
            act = last_action if isinstance(last_action, dict) else (last_action.__dict__ if hasattr(last_action, "__dict__") else {})
            if "navigate" in act:
                url = act["navigate"].get("url", "") if isinstance(act["navigate"], dict) else str(act["navigate"])
                for board_name, board_url in _BOARD_URLS.items():
                    if board_name in url or board_url.split("//")[-1].split("/")[0] in url:
                        current_board = board_name
                        break
            # Track current keyword from input_text actions
            if "input_text" in act:
                text = act["input_text"].get("text", "") if isinstance(act["input_text"], dict) else ""
                if text:
                    current_keyword = text

            # Recover jobs from evaluate() results in real-time
            _try_recover_jobs(action_results, last_action)

            # Build human-readable message for SSE/UI
            friendly = _friendly_step(
                last_action, action_results,
                board=current_board, keyword=current_keyword,
            )
            await emit_agent_event(session_id, "discovery_progress", {
                "board": current_board,
                "step": f"Step {step_count}: {friendly}",
            })
        except Exception:
            pass

    max_steps = 10 * len(boards)  # ~10 steps per board

    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        max_actions_per_step=5,
        use_vision=False,
        max_failures=10,
    )

    async def _stop_browser():
        try:
            await browser.stop()
        except Exception:
            pass

    try:
        await emit_agent_event(session_id, "discovery_progress", {
            "board": "all",
            "step": f"Starting discovery across {len(boards)} boards...",
        })

        result = await asyncio.wait_for(
            agent.run(max_steps=max_steps, on_step_end=on_step_end),
            timeout=300 * len(boards),  # 5 min per board max
        )

        # Parse structured output from done() action
        raw_jobs: List[DiscoveredJobRaw] = []
        try:
            structured = result.final_result()
            if structured and isinstance(structured, str):
                parsed = json.loads(structured)
                if isinstance(parsed, dict) and "jobs" in parsed:
                    raw_jobs = [DiscoveredJobRaw(**j) for j in parsed["jobs"]]
                elif isinstance(parsed, list):
                    raw_jobs = [DiscoveredJobRaw(**j) for j in parsed]
        except Exception:
            logger.debug("Structured output parsing failed", exc_info=True)

        # Fall back to recovered jobs if structured output is empty
        if not raw_jobs and recovered_jobs:
            logger.info(
                "No structured done() output, using %d jobs recovered from step history",
                len(recovered_jobs),
            )
            raw_jobs = recovered_jobs
        elif not raw_jobs:
            final_text = str(result.final_result() or "")
            logger.warning(
                "No structured jobs from agent (steps=%d). Final: %s",
                step_count, final_text[:500],
            )

        listings = _raw_to_listings(raw_jobs)

        logger.info("browser-use discovered %d total jobs (steps=%d)", len(listings), step_count)
        for j in listings:
            logger.info("  [%s] %s @ %s -- %s", j.board.value, j.title, j.company, j.url)

        # Validate URLs
        listings = await _validate_urls(listings)

        await emit_agent_event(session_id, "discovery_progress", {
            "board": "all",
            "step": f"Found {len(listings)} verified jobs across all boards",
            "count": len(listings),
            "progress": 100,
        })

        return listings

    except asyncio.TimeoutError:
        logger.warning(
            "Discovery agent timed out after %d steps, recovering %d jobs from history",
            step_count, len(recovered_jobs),
        )
        await _stop_browser()
        if recovered_jobs:
            listings = _raw_to_listings(recovered_jobs)
            listings = await _validate_urls(listings)
            logger.info("Recovered %d jobs despite timeout", len(listings))
            await emit_agent_event(session_id, "discovery_progress", {
                "board": "all",
                "step": f"Found {len(listings)} verified jobs (search timed out)",
                "count": len(listings),
                "progress": 100,
            })
            return listings
        return []

    except Exception as exc:
        logger.exception("Discovery agent failed: %s", exc)
        if recovered_jobs:
            listings = _raw_to_listings(recovered_jobs)
            logger.info("Recovered %d jobs despite error", len(listings))
            return listings
        return []

    finally:
        await _stop_browser()
