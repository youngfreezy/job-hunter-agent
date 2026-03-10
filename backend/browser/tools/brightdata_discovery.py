# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Bright Data Datasets API discovery -- replaces browser scraping for LinkedIn, Indeed, Glassdoor.

Uses Bright Data's pre-built web scrapers via their Datasets API v3.
No browser needed -- just HTTP API calls that return structured job data.

The API returns an ``apply_link`` field with the direct ATS application URL
(Greenhouse, Lever, Workday, etc.) so the applier can skip board login walls.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aiohttp

from backend.shared.config import settings
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import JobBoard, JobListing, SearchConfig

logger = logging.getLogger(__name__)

# Bright Data Datasets API
_API_BASE = "https://api.brightdata.com/datasets/v3"

# Dataset IDs for each board's job scraper
_BOARD_DATASET_IDS: Dict[str, str] = {
    "linkedin": "gd_lpfll7v5hcqtkxl6l",
    "indeed": "gd_l4dx9j9sscpvs7no2",
    "glassdoor": "gd_lpfbbndm1xnopbrcr0",
}

_BOARD_TO_ENUM: Dict[str, JobBoard] = {
    "linkedin": JobBoard.LINKEDIN,
    "indeed": JobBoard.INDEED,
    "glassdoor": JobBoard.GLASSDOOR,
}

# Polling config
_POLL_INTERVAL = 10  # seconds
_MAX_POLL_TIME = 300  # 5 minutes max wait per board


def _get_api_token() -> str:
    """Get Bright Data API token from settings."""
    token = getattr(settings, "BRIGHT_DATA_API_TOKEN", None)
    if not token:
        raise RuntimeError(
            "BRIGHT_DATA_API_TOKEN not set. Get it from "
            "brightdata.com > Settings > API tokens."
        )
    return token


def _build_inputs(
    board: str,
    search_config: SearchConfig,
) -> List[Dict[str, Any]]:
    """Build the input array for a Bright Data scraper trigger.

    Each board has different required/accepted fields:
    - LinkedIn:   keyword, location, time_range, experience_level, job_type, remote
    - Indeed:     keyword_search, location, country, domain
    - Glassdoor:  keyword, location, country
    """
    inputs = []
    location = search_config.locations[0] if search_config.locations else ""
    # Glassdoor/Indeed require a non-empty location
    default_location = location or "United States"

    for kw in search_config.keywords:
        if board == "indeed":
            entry: Dict[str, Any] = {
                "keyword_search": kw,
                "location": default_location,
                "country": "US",
                "domain": "indeed.com",
            }
        elif board == "glassdoor":
            entry = {
                "keyword": kw,
                "location": default_location,
                "country": "US",
            }
        else:
            # LinkedIn (and any future boards)
            entry = {"keyword": kw, "location": default_location}
            if search_config.remote_only:
                entry["remote"] = "Remote"
            # Only set experience_level if we have a valid mapped value
            if getattr(search_config, "experience_level", None):
                level_map = {
                    "entry": "Entry level",
                    "mid": "Mid-Senior level",
                    "senior": "Mid-Senior level",
                    "executive": "Executive",
                }
                mapped = level_map.get(search_config.experience_level)
                if mapped:
                    entry["experience_level"] = mapped
            # Only set job_type if we have a valid mapped value
            if getattr(search_config, "job_type", None):
                type_map = {
                    "full-time": "Full-time",
                    "contract": "Contract",
                    "part-time": "Part-time",
                }
                mapped = type_map.get(search_config.job_type)
                if mapped:
                    entry["job_type"] = mapped
            entry["time_range"] = "Past month"

        inputs.append(entry)

    return inputs


def _parse_job(raw: Dict[str, Any], board: str) -> Optional[JobListing]:
    """Parse a raw Bright Data result into a JobListing."""
    try:
        title = raw.get("title") or raw.get("job_title") or raw.get("name", "")
        company = raw.get("company") or raw.get("company_name") or raw.get("employer", "")
        location = raw.get("location") or raw.get("job_location") or ""
        url = raw.get("url") or raw.get("job_url") or raw.get("link", "")

        if not title or not company or not url:
            return None

        salary = raw.get("salary") or raw.get("salary_range") or raw.get("compensation")
        # LinkedIn dataset uses job_base_pay_range
        if not salary:
            salary = raw.get("job_base_pay_range")
        description = raw.get("description") or raw.get("job_description") or raw.get("job_description_formatted") or raw.get("snippet", "")
        posted = raw.get("posted_date") or raw.get("date_posted") or raw.get("posted_at") or raw.get("job_posted_date")
        is_remote = bool(
            raw.get("is_remote")
            or "remote" in location.lower()
            or raw.get("remote") == "Remote"
        )

        # The API returns apply_link with the direct ATS application URL
        apply_link = raw.get("apply_link") or None
        # Only use as external URL if it's not the same board domain
        if apply_link and any(d in apply_link.lower() for d in ("linkedin.com", "indeed.com", "glassdoor.com")):
            apply_link = None

        return JobListing(
            id=str(uuid4()),
            title=title.strip(),
            company=company.strip(),
            location=location.strip(),
            url=url.strip(),
            board=_BOARD_TO_ENUM[board],
            salary_range=str(salary) if salary else None,
            description_snippet=description[:500] if description else None,
            posted_date=str(posted) if posted else None,
            is_remote=is_remote,
            external_apply_url=apply_link,
            discovered_at=datetime.utcnow(),
        )
    except Exception:
        logger.debug("Failed to parse job from %s: %s", board, raw, exc_info=True)
        return None


async def _trigger_scrape(
    session: aiohttp.ClientSession,
    board: str,
    search_config: SearchConfig,
    token: str,
) -> Optional[str]:
    """Trigger a Bright Data scraper and return the snapshot_id."""
    dataset_id = _BOARD_DATASET_IDS.get(board)
    if not dataset_id:
        logger.warning("No Bright Data dataset for board: %s", board)
        return None

    inputs = _build_inputs(board, search_config)
    url = (
        f"{_API_BASE}/scrape"
        f"?dataset_id={dataset_id}"
        f"&notify=false"
        f"&include_errors=true"
        f"&type=discover_new"
        f"&discover_by=keyword"
    )

    try:
        async with session.post(
            url,
            json={"input": inputs},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        ) as resp:
            if resp.status not in (200, 202):
                body = await resp.text()
                logger.error(
                    "Bright Data trigger failed for %s: %d %s",
                    board, resp.status, body[:200],
                )
                return None

            data = await resp.json()
            snapshot_id = data.get("snapshot_id")
            logger.info(
                "Bright Data scrape triggered for %s: snapshot_id=%s",
                board, snapshot_id,
            )
            return snapshot_id

    except Exception:
        logger.error("Failed to trigger Bright Data scrape for %s", board, exc_info=True)
        return None


async def _poll_results(
    session: aiohttp.ClientSession,
    snapshot_id: str,
    board: str,
    token: str,
) -> List[Dict[str, Any]]:
    """Poll for scrape results until ready (HTTP 200) or timeout."""
    url = f"{_API_BASE}/snapshot/{snapshot_id}?format=json"
    headers = {"Authorization": f"Bearer {token}"}

    elapsed = 0
    while elapsed < _MAX_POLL_TIME:
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(
                        "Bright Data results ready for %s: %d records",
                        board, len(data) if isinstance(data, list) else 0,
                    )
                    return data if isinstance(data, list) else []
                elif resp.status == 202:
                    # Still processing
                    pass
                else:
                    body = await resp.text()
                    logger.warning(
                        "Bright Data poll unexpected status for %s: %d %s",
                        board, resp.status, body[:200],
                    )
        except Exception:
            logger.warning("Poll error for %s", board, exc_info=True)

        await asyncio.sleep(_POLL_INTERVAL)
        elapsed += _POLL_INTERVAL

    logger.warning("Bright Data poll timed out for %s after %ds", board, _MAX_POLL_TIME)
    return []


async def _scrape_board_api(
    session: aiohttp.ClientSession,
    board: str,
    search_config: SearchConfig,
    session_id: str,
    token: str,
    max_results: int,
) -> List[JobListing]:
    """Scrape one board via Bright Data Datasets API."""
    await emit_agent_event(session_id, "discovery_progress", {
        "board": board,
        "step": f"Querying {board.title()} via Bright Data API...",
    })

    snapshot_id = await _trigger_scrape(session, board, search_config, token)
    if not snapshot_id:
        await emit_agent_event(session_id, "discovery_progress", {
            "board": board,
            "step": f"Failed to start {board.title()} scrape",
            "error": True,
        })
        return []

    await emit_agent_event(session_id, "discovery_progress", {
        "board": board,
        "step": f"Waiting for {board.title()} results...",
    })

    raw_results = await _poll_results(session, snapshot_id, board, token)

    jobs = []
    for raw in raw_results:
        job = _parse_job(raw, board)
        if job:
            jobs.append(job)

    # Cap results
    jobs = jobs[:max_results]

    await emit_agent_event(session_id, "discovery_progress", {
        "board": board,
        "step": f"Found {len(jobs)} jobs on {board.title()}",
        "count": len(jobs),
    })

    logger.info("Bright Data %s: %d raw -> %d parsed jobs", board, len(raw_results), len(jobs))
    return jobs


async def discover_all_boards(
    boards: List[str],
    search_config: SearchConfig,
    session_id: str,
    max_per_board: int = 20,
) -> List[JobListing]:
    """Discover jobs using Bright Data Datasets API.

    Drop-in replacement for direct_discovery.discover_all_boards().
    Same signature, same return type.
    """
    token = _get_api_token()
    all_jobs: List[JobListing] = []

    # Filter to boards we have dataset IDs for
    supported = [b for b in boards if b in _BOARD_DATASET_IDS]
    unsupported = [b for b in boards if b not in _BOARD_DATASET_IDS]

    if unsupported:
        logger.info("Skipping boards without Bright Data datasets: %s", unsupported)

    timeout = aiohttp.ClientTimeout(total=_MAX_POLL_TIME + 30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Trigger all boards in parallel
        tasks = [
            _scrape_board_api(
                session, board, search_config, session_id, token, max_per_board,
            )
            for board in supported
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for board, result in zip(supported, results):
            if isinstance(result, Exception):
                logger.error("Bright Data %s failed: %s", board, result)
                await emit_agent_event(session_id, "discovery_progress", {
                    "board": board,
                    "step": f"{board.title()} failed: {str(result)[:80]}",
                    "error": True,
                })
            elif result:
                all_jobs.extend(result)
            else:
                await emit_agent_event(session_id, "discovery_progress", {
                    "board": board,
                    "step": f"{board.title()} returned 0 results",
                    "error": True,
                })

    # Log external apply URL stats
    ext_count = sum(1 for j in all_jobs if j.external_apply_url)
    if ext_count:
        logger.info(
            "Bright Data API returned %d/%d jobs with external apply URLs",
            ext_count, len(all_jobs),
        )

    # Handle unsupported boards (e.g. greenhouse_lever) via direct scrapers
    if unsupported:
        try:
            from backend.browser.tools.direct_discovery import (
                discover_all_boards as direct_discover,
            )
            direct_jobs = await direct_discover(
                boards=unsupported,
                search_config=search_config,
                session_id=session_id,
                max_per_board=max_per_board,
            )
            all_jobs.extend(direct_jobs)
        except Exception:
            logger.warning(
                "Direct discovery fallback failed for %s", unsupported,
                exc_info=True,
            )

    await emit_agent_event(session_id, "discovery_progress", {
        "board": "all",
        "step": f"Discovery complete: {len(all_jobs)} jobs found",
        "count": len(all_jobs),
        "progress": 100,
    })

    return all_jobs
