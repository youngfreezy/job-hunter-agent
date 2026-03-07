"""Discovery Agent -- single browser-use agent searches all job boards.

One agent, one browser, all boards sequentially in the same Chrome session.
No per-board restarts, no competing resources. Results are deduplicated.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

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

PER_BOARD_MAX = 20
_SKIP_BOARDS = {JobBoard.GOOGLE_JOBS.value}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_search_config(state: Dict[str, Any]) -> SearchConfig:
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
    return f"{job.title.lower().strip()}|{job.company.lower().strip()}"


# ---------------------------------------------------------------------------
# Main discovery node
# ---------------------------------------------------------------------------

async def run_discovery_agent(state: Dict[str, Any]) -> dict:
    """Discover job listings: Bright Data API first, Playwright fallback."""
    from backend.shared.config import settings

    session_id: str = state.get("session_id", "")
    search_config = _get_search_config(state)

    # Use Bright Data Datasets API when enabled (no browser needed)
    if settings.BRIGHT_DATA_DISCOVERY_ENABLED and settings.BRIGHT_DATA_API_TOKEN:
        from backend.browser.tools.brightdata_discovery import (
            discover_all_boards,
        )
        _BOARD_ORDER = ["linkedin", "indeed", "glassdoor", "greenhouse_lever"]
    else:
        from backend.browser.tools.direct_discovery import discover_all_boards
        _BOARD_ORDER = ["linkedin", "indeed", "glassdoor", "greenhouse_lever"]

    boards = [b for b in _BOARD_ORDER if b not in _SKIP_BOARDS]

    logger.info(
        "Discovery agent starting -- keywords=%s, locations=%s, boards=%s",
        search_config.keywords,
        search_config.locations,
        boards,
    )

    max_per_board = max(PER_BOARD_MAX // len(boards), 5) if boards else PER_BOARD_MAX

    all_jobs = await discover_all_boards(
        boards=boards,
        search_config=search_config,
        session_id=session_id,
        max_per_board=max_per_board,
    )

    # Deduplicate
    seen_keys: set[str] = set()
    deduped: List[JobListing] = []
    for job in all_jobs:
        key = _dedup_key(job)
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(job)

    logger.info(
        "Discovery complete -- %d total jobs (%d after dedup)",
        len(all_jobs), len(deduped),
    )
    for job in deduped:
        logger.info(
            "  [%s] %s @ %s — %s",
            job.board.value if hasattr(job.board, 'value') else job.board,
            job.title, job.company, job.url[:120],
        )

    return {
        "discovered_jobs": deduped,
        "errors": [],
        "agent_statuses": {"discovery": f"done ({len(deduped)} listings)"},
        "status": "scoring",
    }


# ---------------------------------------------------------------------------
# Alias for graph.py compatibility
# ---------------------------------------------------------------------------
run = run_discovery_agent
