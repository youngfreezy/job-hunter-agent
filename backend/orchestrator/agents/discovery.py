"""Discovery Agent -- searches job boards using browser-use AI agents.

Uses browser-use (LLM-driven browser automation) to dynamically navigate
job boards, search keywords, and extract listings. No hardcoded CSS selectors.

Boards are searched sequentially (one at a time), each with a fresh browser
instance (browser-use resets CDP on agent completion). Only 1 Chrome runs
at a time. Results are deduplicated by title+company.
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

    Each board gets a fresh browser (browser-use resets CDP after agent
    completion). Boards run sequentially to keep only 1 Chrome at a time.
    Results are deduplicated by title+company.
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

    # Each board gets its own fresh browser because browser-use's Agent.run()
    # resets/disconnects the browser session on completion, breaking CDP for
    # subsequent agents. Sequential execution keeps only 1 Chrome at a time.
    for board in boards:
        board_label = board.value.replace("_", " ").title()

        await emit_agent_event(session_id, "discovery_progress", {
            "board": board.value,
            "step": f"Searching {board_label}...",
        })

        try:
            board_jobs = await discover_board(
                board=board,
                search_config=search_config,
                session_id=session_id,
                max_results=PER_BOARD_MAX,
                browser=None,  # fresh browser per board
            )

            agent_statuses[f"discovery_{board.value}"] = f"done ({len(board_jobs)} listings)"

            # Deduplicate across boards
            for job in board_jobs:
                key = _dedup_key(job)
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_jobs.append(job)

        except Exception as exc:
            logger.exception("Discovery failed for %s", board.value)
            all_errors.append(f"Discovery failed for {board.value}: {exc}")
            agent_statuses[f"discovery_{board.value}"] = "failed"

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
