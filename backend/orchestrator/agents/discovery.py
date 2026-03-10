# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Discovery Agent -- MCP-based agentic discovery.

Uses Bright Data MCP ``search_engine`` to find jobs directly on ATS
platforms (Greenhouse, Lever, Ashby, Workday, etc.) plus the free
Greenhouse public API.  No browser required, no auth-wall issues.
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
        search_radius=state.get("search_radius", 100),
    )


def _dedup_key(job: JobListing) -> str:
    return f"{job.title.lower().strip()}|{job.company.lower().strip()}"


# ---------------------------------------------------------------------------
# Main discovery node
# ---------------------------------------------------------------------------

async def run_discovery_agent(state: Dict[str, Any]) -> dict:
    """Discover job listings via MCP search + Greenhouse API."""
    from backend.browser.tools.mcp_discovery import discover_all_boards

    session_id: str = state.get("session_id", "")
    search_config = _get_search_config(state)

    # boards param is accepted for interface compat but ignored by MCP discovery
    session_config = state.get("session_config")
    configured_boards: list | None = None
    if session_config:
        cfg = session_config if isinstance(session_config, dict) else (session_config.model_dump() if hasattr(session_config, "model_dump") else {})
        configured_boards = cfg.get("job_boards")

    boards = configured_boards or ["greenhouse", "lever", "ashby", "workday"]

    logger.info(
        "Discovery agent starting -- keywords=%s, locations=%s",
        search_config.keywords,
        search_config.locations,
    )

    # Use max_jobs from session config if set, otherwise PER_BOARD_MAX
    total_max = PER_BOARD_MAX
    if session_config:
        cfg = session_config if isinstance(session_config, dict) else (session_config.model_dump() if hasattr(session_config, "model_dump") else {})
        total_max = cfg.get("max_jobs", PER_BOARD_MAX) or PER_BOARD_MAX
    max_per_board = max(total_max // len(boards), 5) if boards else total_max

    errors: List[str] = []
    try:
        all_jobs = await discover_all_boards(
            boards=boards,
            search_config=search_config,
            session_id=session_id,
            max_per_board=max_per_board,
        )
    except Exception as exc:
        logger.exception("Discovery failed entirely: %s", exc)
        errors.append(f"Discovery failed: {exc}")
        all_jobs = []

    # Deduplicate within this batch
    seen_keys: set[str] = set()
    deduped: List[JobListing] = []
    for job in all_jobs:
        key = _dedup_key(job)
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(job)

    # On backfill rounds, exclude jobs already seen in previous rounds
    # (by title+company since IDs are regenerated each discovery)
    if state.get("backfill_rounds", 0) > 0:
        prev_keys: set[str] = set()
        for prev_job in (state.get("discovered_jobs") or []):
            prev_keys.add(_dedup_key(prev_job))
        before_backfill = len(deduped)
        deduped = [j for j in deduped if _dedup_key(j) not in prev_keys]
        if before_backfill != len(deduped):
            logger.info(
                "Backfill dedup: %d -> %d jobs (excluded %d already seen)",
                before_backfill, len(deduped), before_backfill - len(deduped),
            )

    logger.info(
        "Discovery complete -- %d total jobs (%d after dedup), errors=%s",
        len(all_jobs), len(deduped), errors,
    )
    for job in deduped:
        logger.info(
            "  [%s] %s @ %s — %s",
            job.board.value if hasattr(job.board, 'value') else job.board,
            job.title, job.company, job.url[:120],
        )

    if not deduped:
        await emit_agent_event(session_id, "discovery_progress", {
            "board": "all",
            "step": "No jobs found across any board",
            "error": True,
        })

    return {
        "discovered_jobs": deduped,
        "errors": errors,
        "agent_statuses": {"discovery": f"done ({len(deduped)} listings)"},
        "status": "scoring",
    }


# ---------------------------------------------------------------------------
# Alias for graph.py compatibility
# ---------------------------------------------------------------------------
run = run_discovery_agent
