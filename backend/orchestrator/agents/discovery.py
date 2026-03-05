"""Discovery Agent -- searches job boards using browser-use AI agents.

Uses browser-use (LLM-driven browser automation) to dynamically navigate
job boards, search keywords, and extract listings. No hardcoded CSS selectors.

All boards are searched concurrently via asyncio.gather, each with its own
browser-use Agent and BrowserSession. Results are deduplicated by title+company.
"""

from __future__ import annotations

import asyncio
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

PER_BOARD_MAX = 20  # Overall cap per board after dedup

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


# ---------------------------------------------------------------------------
# Main discovery node
# ---------------------------------------------------------------------------

async def run_discovery_agent(state: Dict[str, Any]) -> dict:
    """Discover job listings across job boards using browser-use.

    Each board gets its own browser-use Agent that dynamically navigates
    the site, searches keywords, and extracts listings. All boards run
    concurrently. Results are deduplicated by title+company.
    """
    from backend.browser.tools.browser_use_discovery import discover_board

    session_id: str = state.get("session_id", "")
    search_config = _get_search_config(state)
    boards = [b for b in JobBoard if b.value not in _SKIP_BOARDS]

    logger.info(
        "Discovery agent starting -- keywords=%s, locations=%s, boards=%s",
        search_config.keywords,
        search_config.locations,
        [b.value for b in boards],
    )

    all_jobs: List[JobListing] = []
    seen_keys: set[str] = set()
    all_errors: List[str] = []
    agent_statuses: Dict[str, str] = {}

    async def _discover_board(board: JobBoard) -> tuple[JobBoard, List[JobListing], List[str]]:
        """Run browser-use discovery for a single board."""
        try:
            jobs = await discover_board(
                board=board,
                search_config=search_config,
                session_id=session_id,
                max_results=PER_BOARD_MAX,
            )
            return board, jobs, []
        except Exception as exc:
            logger.exception("Discovery failed for %s", board.value)
            return board, [], [f"Discovery failed for {board.value}: {exc}"]

    # Discover all boards concurrently
    results = await asyncio.gather(
        *[_discover_board(board) for board in boards],
        return_exceptions=True,
    )

    for result in results:
        if isinstance(result, Exception):
            logger.error("Board discovery failed: %s", result)
            all_errors.append(str(result))
            continue

        board, board_jobs, board_errors = result
        all_errors.extend(board_errors)

        if board_errors and not board_jobs:
            agent_statuses[f"discovery_{board.value}"] = "failed"
        else:
            agent_statuses[f"discovery_{board.value}"] = f"done ({len(board_jobs)} listings)"

        # Deduplicate across boards
        for job in board_jobs:
            key = _dedup_key(job)
            if key not in seen_keys:
                seen_keys.add(key)
                all_jobs.append(job)

    logger.info(
        "Discovery complete -- %d total jobs from %d boards, %d errors",
        len(all_jobs), len(boards), len(all_errors),
    )

    return {
        "discovered_jobs": all_jobs,
        "errors": all_errors,
        "agent_statuses": agent_statuses,
        "status": "scoring",
    }


# ---------------------------------------------------------------------------
# Alias for graph.py compatibility
# ---------------------------------------------------------------------------
run = run_discovery_agent
