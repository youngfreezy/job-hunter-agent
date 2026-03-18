# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Discovery Agent -- Serper-based agentic discovery.

Uses Serper (Google Search API) to find jobs directly on ATS
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

    # Inject Moltbook strategy patches: reorder boards by community-informed priority
    try:
        from backend.moltbook.strategies import get_strategy_manager
        mgr = get_strategy_manager()
        strategy_state = mgr.get_state()
        if strategy_state.board_priorities and not strategy_state.human_review_needed:
            boards = sorted(
                boards,
                key=lambda b: strategy_state.board_priorities.get(b, 0.5),
                reverse=True,
            )
            logger.info("Moltbook strategy: reordered boards to %s", boards)
    except Exception as exc:
        logger.debug("Moltbook strategy injection skipped: %s", exc)

    logger.info(
        "Discovery agent starting -- keywords=%s, locations=%s",
        search_config.keywords,
        search_config.locations,
    )

    await emit_agent_event(session_id, "discovery_progress", {
        "board": "all",
        "step": f"Searching for {', '.join(search_config.keywords[:3])} jobs...",
        "total": 0,
    })

    # Use max_jobs from session config if set, otherwise PER_BOARD_MAX
    total_max = PER_BOARD_MAX
    if session_config:
        cfg = session_config if isinstance(session_config, dict) else (session_config.model_dump() if hasattr(session_config, "model_dump") else {})
        total_max = cfg.get("max_jobs", PER_BOARD_MAX) or PER_BOARD_MAX
    max_per_board = max(total_max // len(boards), 5) if boards else total_max

    # Fetch applied URLs and blocked companies BEFORE discovery so we can
    # pass them into query generation for smarter, more varied searches
    user_id = state.get("user_id", "")
    applied_urls: set[str] = set()
    blocked_companies: set[str] = set()
    if user_id:
        try:
            from backend.shared.application_store import (
                get_previously_applied_urls,
                get_rate_limited_companies,
            )
            applied_urls = get_previously_applied_urls(user_id)
            blocked_companies = get_rate_limited_companies(user_id)
            from backend.shared.billing_store import get_blocked_companies
            blocked_companies = blocked_companies | get_blocked_companies(user_id)
        except Exception:
            logger.warning("Failed to fetch applied URLs for user %s", user_id, exc_info=True)

    round_number = state.get("backfill_rounds", 0)

    errors: List[str] = []
    try:
        all_jobs = await discover_all_boards(
            boards=boards,
            search_config=search_config,
            session_id=session_id,
            max_per_board=max_per_board,
            applied_companies=blocked_companies,
            applied_urls=applied_urls,
            round_number=round_number,
        )
    except Exception as exc:
        logger.exception("Discovery failed entirely: %s", exc)
        errors.append(f"Discovery failed: {exc}")
        all_jobs = []

    await emit_agent_event(session_id, "discovery_progress", {
        "board": "all",
        "step": f"Found {len(all_jobs)} jobs, filtering duplicates...",
        "total": len(all_jobs),
    })

    # Deduplicate within this batch
    seen_keys: set[str] = set()
    deduped: List[JobListing] = []
    for job in all_jobs:
        key = _dedup_key(job)
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(job)

    # Exclude jobs the user has already applied to or from blocked companies
    if user_id and (applied_urls or blocked_companies):
        before_filter = len(deduped)
        deduped = [
            j for j in deduped
            if j.url not in applied_urls
            and j.company.lower().strip() not in blocked_companies
        ]
        excluded = before_filter - len(deduped)
        if excluded:
            logger.info(
                "Discovery pre-filter: excluded %d jobs (applied URLs: %d, blocked companies: %s) for user %s",
                excluded, len(applied_urls), blocked_companies or "none", user_id,
            )
        # Emit filtering stats so user can see why jobs were filtered
        await emit_agent_event(session_id, "discovery_progress", {
            "board": "all",
            "step": f"Found {before_filter} jobs, {excluded} already applied — {len(deduped)} new",
            "total_found": before_filter,
            "already_applied": excluded,
            "new_jobs": len(deduped),
        })

    # On backfill rounds, exclude jobs already seen in previous rounds
    # (by title+company since IDs are regenerated each discovery)
    if round_number > 0:
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

    await emit_agent_event(session_id, "discovery_progress", {
        "board": "all",
        "step": f"{len(deduped)} new jobs ready for scoring" if deduped else "No new jobs found — try different keywords or locations",
        "total": len(deduped),
        "error": not deduped,
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
