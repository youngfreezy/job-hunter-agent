"""Discovery Agent -- searches job boards for listings matching the user's SearchConfig.

Uses real Playwright browser automation (patchright) to scrape job boards
sequentially through a single shared browser instance. Each board gets its
own isolated BrowserContext but shares the same Chromium process to avoid
resource exhaustion.

Keywords are searched individually (one at a time) per board to avoid the
"keyword stuffing" problem where boards return no results for overly
specific multi-keyword queries. Results are deduplicated by title+company.
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

PER_KEYWORD_MAX = 8  # Max results per keyword per board
PER_BOARD_MAX = 20   # Overall cap per board after dedup

# Map board enum values to their scraper import paths (lazy-loaded)
_SCRAPER_REGISTRY: Dict[str, str] = {
    JobBoard.INDEED.value: "backend.browser.tools.job_boards.indeed",
    JobBoard.LINKEDIN.value: "backend.browser.tools.job_boards.linkedin",
    JobBoard.GLASSDOOR.value: "backend.browser.tools.job_boards.glassdoor",
    JobBoard.ZIPRECRUITER.value: "backend.browser.tools.job_boards.ziprecruiter",
}

_SCRAPER_FUNCTIONS: Dict[str, str] = {
    JobBoard.INDEED.value: "scrape_indeed",
    JobBoard.LINKEDIN.value: "scrape_linkedin",
    JobBoard.GLASSDOOR.value: "scrape_glassdoor",
    JobBoard.ZIPRECRUITER.value: "scrape_ziprecruiter",
}

# Boards to skip entirely
_SKIP_BOARDS = {JobBoard.GOOGLE_JOBS.value}

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


def _dedup_key(job: JobListing) -> str:
    """Generate a dedup key from title + company (lowercased, stripped)."""
    return f"{job.title.lower().strip()}|{job.company.lower().strip()}"


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
# Main discovery node — scrapes boards sequentially, keywords individually
# ---------------------------------------------------------------------------

async def run_discovery_agent(state: Dict[str, Any]) -> dict:
    """Discover job listings across job boards.

    Searches each keyword individually per board to avoid the keyword-stuffing
    problem. Results are deduplicated by title+company across all searches.
    """
    from backend.browser.manager import BrowserManager

    session_id: str = state.get("session_id", "")
    search_config = _get_search_config(state)
    boards = [b.value for b in JobBoard if b.value not in _SKIP_BOARDS]

    logger.info(
        "Discovery agent starting -- keywords=%s, locations=%s, boards=%s",
        search_config.keywords,
        search_config.locations,
        boards,
    )

    all_jobs: List[JobListing] = []
    seen_keys: set[str] = set()
    all_errors: List[str] = []
    agent_statuses: Dict[str, str] = {}

    manager = BrowserManager()
    try:
        await manager.start()

        total_steps = len(boards) * max(len(search_config.keywords), 1)
        step_idx = 0

        for board in boards:
            board_label = board.replace("_", " ").title()
            board_jobs: List[JobListing] = []

            scraper = await _get_scraper(board)
            if scraper is None:
                msg = f"No scraper available for {board}"
                logger.warning(msg)
                all_errors.append(msg)
                agent_statuses[f"discovery_{board}"] = "failed -- no scraper"
                step_idx += max(len(search_config.keywords), 1)
                continue

            # Search each keyword individually
            keywords = search_config.keywords if search_config.keywords else [""]
            for kw in keywords:
                if len(board_jobs) >= PER_BOARD_MAX:
                    step_idx += 1
                    continue

                step_idx += 1
                pct = int((step_idx / total_steps) * 100)

                kw_label = kw or "general search"
                await emit_agent_event(session_id, "discovery_progress", {
                    "board": board,
                    "step": f"Searching {board_label} for \"{kw_label}\"...",
                    "progress": pct,
                })

                # Build a single-keyword config for this search
                single_kw_config = SearchConfig(
                    keywords=[kw] if kw else [],
                    locations=search_config.locations,
                    remote_only=search_config.remote_only,
                    salary_min=search_config.salary_min,
                    experience_level=getattr(search_config, "experience_level", None),
                    job_type=getattr(search_config, "job_type", None),
                )

                ctx_id = None
                try:
                    ctx_id, context = await manager.new_context()
                    logger.info(
                        "Scraping %s for keyword \"%s\" (context=%s)",
                        board, kw_label, ctx_id,
                    )

                    listings = await scraper(
                        context,
                        single_kw_config,
                        max_results=PER_KEYWORD_MAX,
                    )

                    # Deduplicate against all previous results
                    new_count = 0
                    for job in listings:
                        key = _dedup_key(job)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            board_jobs.append(job)
                            new_count += 1

                    logger.info(
                        "Scraper %s/%s returned %d listings (%d new)",
                        board, kw_label, len(listings), new_count,
                    )

                except Exception as scrape_err:
                    logger.exception("Scraping failed for %s/%s", board, kw_label)
                    err_msg = f"Scraping failed for {board}/{kw_label}: {scrape_err}"
                    all_errors.append(err_msg)

                finally:
                    if ctx_id:
                        await manager.close_context(ctx_id)

            # Board summary
            all_jobs.extend(board_jobs[:PER_BOARD_MAX])
            agent_statuses[f"discovery_{board}"] = f"done ({len(board_jobs)} listings)"

            await emit_agent_event(session_id, "discovery_progress", {
                "board": board,
                "step": f"Found {len(board_jobs)} jobs on {board_label}",
                "count": len(board_jobs),
                "progress": 100,
            })

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
