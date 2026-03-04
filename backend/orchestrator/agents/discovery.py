"""Discovery Agent -- searches job boards for listings matching the user's SearchConfig.

Uses real Playwright browser automation to scrape job boards in parallel via
LangGraph's Send API.  Falls back to Claude-generated simulated listings if
scraping fails or if SIMULATE_DISCOVERY is enabled.
"""

from __future__ import annotations

import json
import logging
import random
from typing import Any, Callable, Coroutine, Dict, List, Optional
from uuid import uuid4

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Send

from backend.shared.config import settings
from backend.shared.models.schemas import (
    ATSType,
    JobBoard,
    JobListing,
    SearchConfig,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-6"
DISCOVERY_MIN_RESULTS = 20
DISCOVERY_MAX_RESULTS = 50
# Per-board max when scraping (aggregate across all boards will hit 20-50)
PER_BOARD_MAX = 12

BOARDS = list(JobBoard)
ATS_TYPES = list(ATSType)

# Map board enum values to their scraper import paths (lazy-loaded)
_SCRAPER_REGISTRY: Dict[str, str] = {
    JobBoard.INDEED.value: "backend.browser.tools.job_boards.indeed",
    JobBoard.LINKEDIN.value: "backend.browser.tools.job_boards.linkedin",
    JobBoard.GLASSDOOR.value: "backend.browser.tools.job_boards.glassdoor",
    JobBoard.ZIPRECRUITER.value: "backend.browser.tools.job_boards.ziprecruiter",
    JobBoard.GOOGLE_JOBS.value: "backend.browser.tools.job_boards.google_jobs",
}

_SCRAPER_FUNCTIONS: Dict[str, str] = {
    JobBoard.INDEED.value: "scrape_indeed",
    JobBoard.LINKEDIN.value: "scrape_linkedin",
    JobBoard.GLASSDOOR.value: "scrape_glassdoor",
    JobBoard.ZIPRECRUITER.value: "scrape_ziprecruiter",
    JobBoard.GOOGLE_JOBS.value: "scrape_google_jobs",
}

# ---------------------------------------------------------------------------
# Simulation prompt (kept as fallback)
# ---------------------------------------------------------------------------

SIMULATION_SYSTEM_PROMPT = """\
You are a realistic job-listing generator used for development and testing.
Given a search configuration, produce a JSON array of realistic job listings.

Each listing object MUST have these fields:
- title (str): realistic job title matching the keywords
- company (str): realistic company name (mix of well-known and lesser-known companies)
- location (str): city/state or "Remote" matching the search locations
- url (str): a plausible job-board URL (e.g. https://www.indeed.com/viewjob?jk=abc123)
- salary_range (str | null): e.g. "$120,000 - $160,000/year" or null
- description_snippet (str): 2-3 sentence description of the role
- posted_date (str): a realistic recent date in YYYY-MM-DD format within the last 30 days
- is_remote (bool): whether the role is remote
- is_easy_apply (bool): randomly true ~30% of the time

Rules:
- Make titles, companies, and descriptions diverse and realistic.
- Salary ranges should be plausible for the role level.
- Vary seniority, company size, and tech stacks in the descriptions.
- Return ONLY valid JSON -- an array of objects. No markdown, no explanation.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_search_config(state: Dict[str, Any]) -> SearchConfig:
    """Extract or build a SearchConfig from pipeline state."""
    search_config = state.get("search_config")
    if search_config is not None:
        return search_config

    return SearchConfig(
        keywords=state.get("keywords", []),
        locations=state.get("locations", ["Remote"]),
        remote_only=state.get("remote_only", False),
        salary_min=state.get("salary_min"),
    )


async def _get_scraper(board: str) -> Optional[Callable]:
    """Lazily import and return the scraper function for *board*."""
    module_path = _SCRAPER_REGISTRY.get(board)
    func_name = _SCRAPER_FUNCTIONS.get(board)
    if not module_path or not func_name:
        logger.warning("No scraper registered for board: %s", board)
        return None

    try:
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, func_name)
    except Exception:
        logger.exception("Failed to import scraper for %s", board)
        return None


# ---------------------------------------------------------------------------
# Fan-out dispatch (used by graph.py conditional edges)
# ---------------------------------------------------------------------------

def dispatch_discovery(state: Dict[str, Any]) -> List[Send]:
    """Return one Send per job board for parallel scraping.

    Each Send carries the full state plus a ``board`` key indicating which
    board the discovery node should scrape.
    """
    boards = [b.value for b in JobBoard]
    sends = []
    for board in boards:
        sends.append(Send("discovery", {**state, "board": board}))
    logger.info("Dispatching discovery to %d boards: %s", len(sends), boards)
    return sends


# ---------------------------------------------------------------------------
# Per-board scraping via Playwright
# ---------------------------------------------------------------------------

async def _scrape_board(
    board: str,
    search_config: SearchConfig,
    max_results: int = PER_BOARD_MAX,
) -> List[JobListing]:
    """Scrape a single job board using Playwright.

    Acquires a BrowserManager, creates an isolated context, calls the
    board-specific scraper, and cleans up.

    Raises on failure so the caller can fall back to simulation.
    """
    from backend.browser.manager import BrowserManager

    scraper = await _get_scraper(board)
    if scraper is None:
        raise ValueError(f"No scraper available for board: {board}")

    manager = BrowserManager()
    ctx_id = None

    try:
        await manager.start()
        ctx_id, context = await manager.new_context()

        logger.info("Scraping %s (context=%s) ...", board, ctx_id)
        listings = await scraper(
            context,
            search_config,
            max_results=max_results,
        )
        logger.info(
            "Scraper for %s returned %d listings", board, len(listings)
        )
        return listings

    finally:
        if ctx_id:
            await manager.close_context(ctx_id)
        await manager.stop()


# ---------------------------------------------------------------------------
# Simulated discovery (fallback)
# ---------------------------------------------------------------------------

async def _simulate_board(
    board: str,
    search_config: SearchConfig,
    num_listings: int = 8,
) -> List[JobListing]:
    """Generate simulated job listings via Claude for a specific board.

    Used as a fallback when Playwright scraping fails or when
    SIMULATE_DISCOVERY is enabled.
    """
    llm = ChatAnthropic(
        model=DEFAULT_MODEL,
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=4096,
        temperature=1.0,
    )

    board_display = board.replace("_", " ").title()
    user_prompt = (
        f"Generate exactly {num_listings} job listings for the {board_display} "
        f"job board for this search:\n"
        f"- Keywords: {', '.join(search_config.keywords)}\n"
        f"- Locations: {', '.join(search_config.locations)}\n"
        f"- Remote only: {search_config.remote_only}\n"
        f"- Salary minimum: {search_config.salary_min or 'not specified'}\n"
        f"- Experience level: {search_config.experience_level or 'not specified'}\n"
        f"- Job type: {search_config.job_type or 'full-time'}\n"
    )

    response = await llm.ainvoke([
        SystemMessage(content=SIMULATION_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    raw_text = response.content
    if isinstance(raw_text, list):
        raw_text = "".join(
            block if isinstance(block, str) else block.get("text", "")
            for block in raw_text
        )

    raw_listings: List[dict] = json.loads(raw_text)

    # Convert to the board-specific enum
    board_enum = JobBoard(board) if board in [b.value for b in JobBoard] else random.choice(BOARDS)

    discovered: List[JobListing] = []
    for item in raw_listings:
        listing = JobListing(
            id=str(uuid4()),
            title=item["title"],
            company=item["company"],
            location=item["location"],
            url=item.get(
                "url",
                f"https://www.indeed.com/viewjob?jk={uuid4().hex[:12]}",
            ),
            board=board_enum,
            ats_type=random.choice(ATS_TYPES),
            salary_range=item.get("salary_range"),
            description_snippet=item.get("description_snippet"),
            posted_date=item.get("posted_date"),
            is_remote=item.get("is_remote", False),
            is_easy_apply=item.get("is_easy_apply", False),
        )
        discovered.append(listing)

    return discovered


# ---------------------------------------------------------------------------
# Main discovery node function (called per-board via Send)
# ---------------------------------------------------------------------------

async def run_discovery_agent(state: Dict[str, Any]) -> dict:
    """Discover job listings for a single board.

    This function is invoked once per board via LangGraph's Send API.
    The ``board`` key in state indicates which board to scrape.

    Strategy:
    1. If SIMULATE_DISCOVERY is True, go straight to simulation.
    2. Otherwise, attempt real Playwright scraping.
    3. If scraping fails, fall back to simulated results.
    4. Return discovered jobs for this board (merged via operator.add).
    """
    board: str = state.get("board", JobBoard.INDEED.value)
    search_config = _get_search_config(state)

    logger.info(
        "Discovery agent starting for board=%s -- keywords=%s, locations=%s",
        board,
        search_config.keywords,
        search_config.locations,
    )

    discovered: List[JobListing] = []
    used_simulation = False

    # --- Attempt real scraping (unless simulation is forced) ---
    if settings.SIMULATE_DISCOVERY:
        logger.info(
            "SIMULATE_DISCOVERY=True -- using simulated results for %s", board
        )
        used_simulation = True
    else:
        try:
            discovered = await _scrape_board(board, search_config)
            logger.info(
                "Playwright scraping succeeded for %s -- %d listings",
                board,
                len(discovered),
            )
        except Exception as scrape_err:
            logger.warning(
                "Playwright scraping failed for %s: %s -- falling back to simulation",
                board,
                scrape_err,
            )
            used_simulation = True

    # --- Fallback to simulation ---
    if used_simulation or not discovered:
        try:
            num = random.randint(6, PER_BOARD_MAX)
            discovered = await _simulate_board(board, search_config, num_listings=num)
            logger.info(
                "Simulation fallback for %s produced %d listings",
                board,
                len(discovered),
            )
        except Exception as sim_err:
            logger.exception("Simulation also failed for %s", board)
            return {
                "discovered_jobs": [],
                "errors": [f"discovery failed for {board}: {sim_err}"],
                "agent_statuses": {f"discovery_{board}": "failed"},
            }

    status_msg = (
        f"done ({len(discovered)} listings"
        f"{', simulated' if used_simulation else ', scraped'})"
    )

    return {
        "discovered_jobs": discovered,
        "agent_statuses": {f"discovery_{board}": status_msg},
        "status": "scoring",
    }


# ---------------------------------------------------------------------------
# Alias for graph.py compatibility
# ---------------------------------------------------------------------------
run = run_discovery_agent
