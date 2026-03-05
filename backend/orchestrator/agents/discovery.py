"""Discovery Agent -- searches job boards for listings matching the user's SearchConfig.

Uses real Playwright browser automation (patchright) to scrape job boards
sequentially through a single shared browser instance. Each board gets its
own isolated BrowserContext but shares the same Chromium process to avoid
resource exhaustion.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

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
# Main discovery node — scrapes ALL boards sequentially with one browser
# ---------------------------------------------------------------------------

async def run_discovery_agent(state: Dict[str, Any]) -> dict:
    """Discover job listings across all job boards.

    Uses a single shared browser process and scrapes each board sequentially
    with an isolated context per board. This prevents resource exhaustion
    from launching 5 separate Chromium processes in parallel.
    """
    from backend.browser.manager import BrowserManager

    session_id: str = state.get("session_id", "")
    search_config = _get_search_config(state)
    boards = [b.value for b in JobBoard]

    logger.info(
        "Discovery agent starting -- keywords=%s, locations=%s, boards=%s",
        search_config.keywords,
        search_config.locations,
        boards,
    )

    all_jobs: List[JobListing] = []
    all_errors: List[str] = []
    agent_statuses: Dict[str, str] = {}

    manager = BrowserManager()
    try:
        await manager.start()

        for board in boards:
            board_label = board.replace("_", " ").title()

            await emit_agent_event(session_id, "discovery_progress", {
                "board": board,
                "step": f"Searching {board_label}...",
                "progress": 0,
            })

            scraper = await _get_scraper(board)
            if scraper is None:
                msg = f"No scraper available for {board}"
                logger.warning(msg)
                all_errors.append(msg)
                agent_statuses[f"discovery_{board}"] = "failed -- no scraper"
                continue

            ctx_id = None
            try:
                ctx_id, context = await manager.new_context()
                logger.info("Scraping %s (context=%s) ...", board, ctx_id)

                listings = await scraper(
                    context,
                    search_config,
                    max_results=PER_BOARD_MAX,
                )

                logger.info("Scraper for %s returned %d listings", board, len(listings))
                all_jobs.extend(listings)
                agent_statuses[f"discovery_{board}"] = f"done ({len(listings)} listings scraped)"

                await emit_agent_event(session_id, "discovery_progress", {
                    "board": board,
                    "step": f"Found {len(listings)} jobs on {board_label}",
                    "count": len(listings),
                    "progress": 100,
                })

            except Exception as scrape_err:
                logger.exception("Scraping failed for %s", board)
                err_msg = f"Scraping failed for {board}: {scrape_err}"
                all_errors.append(err_msg)
                agent_statuses[f"discovery_{board}"] = f"failed -- {scrape_err}"

                await emit_agent_event(session_id, "discovery_progress", {
                    "board": board,
                    "step": f"Scraping failed for {board_label}: {scrape_err}",
                    "progress": 100,
                })

            finally:
                if ctx_id:
                    await manager.close_context(ctx_id)

    finally:
        await manager.stop()

    logger.info(
        "Discovery complete -- %d total jobs from %d boards, %d errors",
        len(all_jobs), len(boards), len(all_errors),
    )

    return {
        "discovered_jobs": all_jobs,
        "errors": all_errors if all_errors else [],
        "agent_statuses": agent_statuses,
        "status": "scoring",
    }


# ---------------------------------------------------------------------------
# Alias for graph.py compatibility
# ---------------------------------------------------------------------------
run = run_discovery_agent
