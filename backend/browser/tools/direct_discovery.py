"""Direct Playwright discovery -- fast scraping using existing per-board scrapers.

Uses the dedicated scrapers in ``job_boards/`` (linkedin.py, indeed.py, etc.)
with BrowserManager for anti-detection.  Falls back to browser-use for boards
where direct scraping returns 0 results.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

import aiohttp

from backend.browser.manager import BrowserManager
from backend.browser.tools.job_boards import (
    rank_by_relevance,
    scrape_glassdoor,
    scrape_indeed,
    scrape_linkedin,
    scrape_ziprecruiter,
)
from backend.browser.tools.job_boards.greenhouse_boards import scrape_greenhouse_lever
from backend.shared.config import settings
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import JobListing, SearchConfig

logger = logging.getLogger(__name__)

# Board name -> scraper function
_BOARD_SCRAPERS = {
    "linkedin": scrape_linkedin,
    "indeed": scrape_indeed,
    "glassdoor": scrape_glassdoor,
    "ziprecruiter": scrape_ziprecruiter,
    "greenhouse_lever": scrape_greenhouse_lever,
}

# Per-board timeout (higher to allow per-keyword searches)
_BOARD_TIMEOUT = 180
# Bright Data remote browser is slower (CAPTCHA solving + network latency)
_BOARD_TIMEOUT_BRIGHTDATA = 300

# Collect broadly, then rank down to this many per board
_COLLECT_CAP = 50
_RETURN_PER_BOARD = 7


async def _scrape_board(
    board: str,
    manager: BrowserManager,
    search_config: SearchConfig,
    session_id: str,
    max_results: int,
) -> List[JobListing]:
    """Scrape a single board, rank results by relevance, return top N."""
    scraper_fn = _BOARD_SCRAPERS.get(board)
    if not scraper_fn:
        logger.warning("No direct scraper for board %s, skipping", board)
        return []

    await emit_agent_event(session_id, "discovery_progress", {
        "board": board,
        "step": f"Searching {board.title()}...",
    })

    ctx_id, context = await manager.new_context(
        proxy=settings.PROXY_URL,
    )
    timeout = _BOARD_TIMEOUT_BRIGHTDATA if manager._mode == "brightdata" else _BOARD_TIMEOUT
    try:
        # Collect broadly -- scrapers search per-keyword internally
        listings = await asyncio.wait_for(
            scraper_fn(context, search_config, max_results=_COLLECT_CAP),
            timeout=timeout,
        )
        logger.info("Direct scrape of %s: %d raw jobs", board, len(listings))

        # LLM-rank and return top N per board
        if listings:
            ranked = await rank_by_relevance(
                listings, search_config.keywords, limit=max_results,
            )
            logger.info(
                "Ranked %s: %d -> %d jobs", board, len(listings), len(ranked),
            )
            await emit_agent_event(session_id, "discovery_progress", {
                "board": board,
                "step": f"Found {len(ranked)} top jobs on {board.title()}",
                "count": len(ranked),
            })
            return ranked

        return []

    except asyncio.TimeoutError:
        logger.warning("Direct scrape of %s timed out after %ds", board, timeout)
        return []
    except Exception:
        logger.warning("Direct scrape of %s failed", board, exc_info=True)
        return []
    finally:
        await manager.close_context(ctx_id)


async def _validate_urls(jobs: List[JobListing]) -> List[JobListing]:
    """Filter out jobs with dead URLs via async HEAD requests."""
    if not jobs:
        return jobs

    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async def _check(job: JobListing) -> Optional[JobListing]:
            try:
                async with session.head(
                    job.url, allow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0"},
                ) as resp:
                    return job if resp.status < 400 else None
            except Exception:
                return job  # benefit of the doubt

        results = await asyncio.gather(*[_check(j) for j in jobs])

    valid = [j for j in results if j is not None]
    dropped = len(jobs) - len(valid)
    if dropped:
        logger.info("URL validation dropped %d/%d jobs", dropped, len(jobs))
    return valid


async def discover_all_boards(
    boards: List[str],
    search_config: SearchConfig,
    session_id: str,
    max_per_board: int = _RETURN_PER_BOARD,
) -> List[JobListing]:
    """Hybrid discovery: direct Playwright first, browser-use fallback.

    Same signature as ``browser_use_discovery.discover_all_boards`` so the
    caller in ``discovery.py`` doesn't need any changes beyond the import.
    """
    all_jobs: List[JobListing] = []
    fallback_boards: List[str] = []

    # Boards that always get blocked locally (CAPTCHAs) -- route directly to
    # Bright Data Scraping Browser to avoid wasting time on doomed attempts.
    _BRIGHTDATA_ONLY_BOARDS = {"indeed", "glassdoor"}

    # Split boards into local-capable and Bright-Data-only
    local_boards = [b for b in boards if b not in _BRIGHTDATA_ONLY_BOARDS]
    bd_direct_boards = [
        b for b in boards
        if b in _BRIGHTDATA_ONLY_BOARDS and b in _BOARD_SCRAPERS
    ]

    # Phase 1: Local Playwright for boards that work locally (LinkedIn, etc.)
    if local_boards:
        manager = BrowserManager()
        await manager.start_for_task(purpose="discovery", headless=settings.BROWSER_HEADLESS)
        try:
            for board in local_boards:
                if board not in _BOARD_SCRAPERS:
                    fallback_boards.append(board)
                    continue

                board_max = max_per_board * 3 if board == "greenhouse_lever" else max_per_board
                listings = await _scrape_board(
                    board, manager, search_config, session_id, board_max,
                )
                if listings:
                    all_jobs.extend(listings)
                else:
                    logger.info(
                        "Board %s returned 0 results, queued for fallback", board,
                    )
                    fallback_boards.append(board)
        finally:
            await manager.stop()

    # Phase 2: Bright Data Scraping Browser for CAPTCHA-protected boards
    # (Indeed, Glassdoor) + any local boards that returned 0 results.
    bd_boards = bd_direct_boards + [b for b in fallback_boards if b in _BOARD_SCRAPERS]
    bd_remaining: List[str] = [b for b in fallback_boards if b not in _BOARD_SCRAPERS]

    if bd_boards and settings.BRIGHT_DATA_BROWSER_ENABLED:
        logger.info(
            "Scraping via Bright Data Scraping Browser (CAPTCHA-solving): %s",
            bd_boards,
        )
        await emit_agent_event(session_id, "discovery_progress", {
            "board": "all",
            "step": f"Searching {', '.join(b.title() for b in bd_boards)} via Bright Data...",
        })
        # Fresh Bright Data session per board — each connect_over_cdp gives a
        # new remote browser, preventing session expiry between boards.
        for board in bd_boards:
            bd_manager = BrowserManager()
            try:
                await bd_manager.start_brightdata()
                listings = await _scrape_board(
                    board, bd_manager, search_config, session_id, max_per_board,
                )
                if listings:
                    all_jobs.extend(listings)
                else:
                    logger.info(
                        "Bright Data scrape of %s returned 0, queued for browser-use",
                        board,
                    )
                    bd_remaining.append(board)
            except Exception:
                logger.warning(
                    "Bright Data browser failed for %s, queuing for browser-use",
                    board,
                    exc_info=True,
                )
                bd_remaining.append(board)
            finally:
                await bd_manager.stop()
    elif bd_boards:
        # Bright Data not enabled -- send directly to browser-use
        bd_remaining.extend(bd_boards)

    # Phase 3: browser-use AI agent as last resort
    if bd_remaining:
        logger.info("Falling back to browser-use for: %s", bd_remaining)
        await emit_agent_event(session_id, "discovery_progress", {
            "board": "all",
            "step": f"Using AI agent for {', '.join(bd_remaining)}...",
        })
        try:
            from backend.browser.tools.browser_use_discovery import (
                discover_all_boards as bu_discover,
            )
            fallback_jobs = await bu_discover(
                boards=bd_remaining,
                search_config=search_config,
                session_id=session_id,
                max_per_board=max_per_board,
            )
            all_jobs.extend(fallback_jobs)
        except Exception:
            logger.warning("Browser-use fallback failed", exc_info=True)

    # Skip URL validation -- job board URLs commonly reject HEAD requests
    # (auth walls, cookie requirements, GET-only) but are still valid listings.
    # The scrapers already verified these exist on real pages.

    await emit_agent_event(session_id, "discovery_progress", {
        "board": "all",
        "step": f"Discovery complete: {len(all_jobs)} verified jobs",
        "count": len(all_jobs),
        "progress": 100,
    })

    return all_jobs
