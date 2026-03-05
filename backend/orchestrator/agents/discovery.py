"""Discovery Agent -- searches job boards for listings matching the user's SearchConfig.

Uses real Playwright browser automation (patchright) to scrape job boards in
parallel via LangGraph's Send API.  Fails loudly if scraping fails -- no
simulation fallbacks.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from langgraph.types import Send

from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import (
    JobBoard,
    JobListing,
    SearchConfig,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Per-board max when scraping (aggregate across all boards will hit 20-50)
PER_BOARD_MAX = 12

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
    """Scrape a single job board using Playwright (patchright).

    Acquires a BrowserManager, creates an isolated context, calls the
    board-specific scraper, and cleans up.  Raises on failure.
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
# Main discovery node function (called per-board via Send)
# ---------------------------------------------------------------------------

async def run_discovery_agent(state: Dict[str, Any]) -> dict:
    """Discover job listings for a single board.

    This function is invoked once per board via LangGraph's Send API.
    The ``board`` key in state indicates which board to scrape.
    Fails with a clear error if scraping fails -- no simulation fallback.
    """
    board: str = state.get("board", JobBoard.INDEED.value)
    session_id: str = state.get("session_id", "")
    search_config = _get_search_config(state)

    logger.info(
        "Discovery agent starting for board=%s -- keywords=%s, locations=%s",
        board,
        search_config.keywords,
        search_config.locations,
    )

    await emit_agent_event(session_id, "discovery_progress", {
        "board": board,
        "step": f"Searching {board.replace('_', ' ').title()}...",
        "progress": 0,
    })

    try:
        discovered = await _scrape_board(board, search_config)
        logger.info(
            "Playwright scraping succeeded for %s -- %d listings",
            board,
            len(discovered),
        )
    except Exception as scrape_err:
        logger.exception("Scraping failed for %s", board)
        await emit_agent_event(session_id, "discovery_progress", {
            "board": board,
            "step": f"Scraping failed for {board.replace('_', ' ').title()}: {scrape_err}",
            "progress": 100,
        })
        return {
            "discovered_jobs": [],
            "errors": [f"Scraping failed for {board}: {scrape_err}"],
            "agent_statuses": {f"discovery_{board}": f"failed -- {scrape_err}"},
        }

    status_msg = f"done ({len(discovered)} listings scraped)"

    await emit_agent_event(session_id, "discovery_progress", {
        "board": board,
        "step": f"Found {len(discovered)} jobs on {board.replace('_', ' ').title()}",
        "count": len(discovered),
        "progress": 100,
    })

    return {
        "discovered_jobs": discovered,
        "agent_statuses": {f"discovery_{board}": status_msg},
        "status": "scoring",
    }


# ---------------------------------------------------------------------------
# Alias for graph.py compatibility
# ---------------------------------------------------------------------------
run = run_discovery_agent
