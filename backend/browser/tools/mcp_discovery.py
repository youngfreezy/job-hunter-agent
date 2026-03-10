# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""MCP-based agentic discovery -- uses Bright Data MCP free tier to find jobs.

Instead of scraping LinkedIn/Indeed/Glassdoor (auth-walled), searches for jobs
directly on ATS platforms (Greenhouse, Lever, Ashby, Workday, etc.) using
Bright Data's search_engine and scrape_as_markdown MCP tools (free tier).

The LLM generates smart search queries targeting ATS sites, then parses
results into JobListing objects. Combined with the Greenhouse API scraper
for comprehensive coverage.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.browser.tools.mcp_client import mcp_search, mcp_session
from backend.shared.event_bus import emit_agent_event
from backend.shared.llm import build_llm, HAIKU_MODEL
from backend.shared.models.schemas import ATSType, JobBoard, JobListing, SearchConfig
from backend.shared.prompt_registry import get_active_prompt

logger = logging.getLogger(__name__)

# ATS domains we want to find jobs on (no auth wall, direct apply)
_ATS_DOMAINS = {
    "greenhouse.io": ATSType.GREENHOUSE,
    "boards.greenhouse.io": ATSType.GREENHOUSE,
    "lever.co": ATSType.LEVER,
    "jobs.lever.co": ATSType.LEVER,
    "ashbyhq.com": ATSType.ASHBY,
    "jobs.ashbyhq.com": ATSType.ASHBY,
    "myworkdayjobs.com": ATSType.WORKDAY,
    "smartrecruiters.com": ATSType.UNKNOWN,
    "icims.com": ATSType.ICIMS,
    "jobvite.com": ATSType.UNKNOWN,
    "workable.com": ATSType.UNKNOWN,
    "breezy.hr": ATSType.UNKNOWN,
}

# Domains to exclude (auth-walled job boards)
_BOARD_DOMAINS = {"linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com"}

_SEARCH_QUERY_PROMPT = """\
You are a job search expert. Generate {num_queries} Google search queries to find \
job listings on ATS platforms (NOT on LinkedIn, Indeed, or Glassdoor).

Target these ATS sites specifically:
- boards.greenhouse.io
- jobs.lever.co
- jobs.ashbyhq.com
- myworkdayjobs.com
- jobs.smartrecruiters.com

Job criteria:
- Keywords: {keywords}
- Remote only: {remote_only}
- Location: {location}

Generate diverse queries using site: operators and keyword variations. \
Each query should target a different ATS platform or keyword combination. \
Focus on finding CURRENT job postings (2026).

Return a JSON array of query strings, nothing else. Example:
["Senior Software Engineer remote site:boards.greenhouse.io", "AI engineer site:jobs.lever.co 2026"]
"""

_PARSE_RESULTS_PROMPT = """\
Parse these job search results into structured job listings. \
Extract ONLY jobs hosted on ATS platforms (greenhouse.io, lever.co, ashbyhq.com, \
myworkdayjobs.com, smartrecruiters.com, etc.).

IGNORE any results from linkedin.com, indeed.com, glassdoor.com, or ziprecruiter.com.

Search results:
{results}

Return a JSON array of objects with these fields:
- title: job title (string)
- company: company name (string)
- location: job location or "Remote" (string)
- url: the direct ATS URL (string, must be on an ATS domain)
- salary: salary range if mentioned (string or null)
- description: brief description (string, max 200 chars)
- is_remote: whether it's remote (boolean)

Only include jobs where you can determine the title, company, and URL. \
Return valid JSON array only, no other text.
"""


def _detect_ats_type(url: str) -> ATSType:
    """Detect ATS type from URL domain."""
    url_lower = url.lower()
    for domain, ats_type in _ATS_DOMAINS.items():
        if domain in url_lower:
            return ats_type
    return ATSType.UNKNOWN


def _is_ats_url(url: str) -> bool:
    """Check if URL is on a known ATS domain."""
    url_lower = url.lower()
    return any(domain in url_lower for domain in _ATS_DOMAINS)


def _is_board_url(url: str) -> bool:
    """Check if URL is on an auth-walled job board."""
    url_lower = url.lower()
    return any(domain in url_lower for domain in _BOARD_DOMAINS)


async def _generate_search_queries(
    search_config: SearchConfig,
    num_queries: int = 8,
) -> List[str]:
    """Use LLM to generate smart search queries targeting ATS sites."""
    llm = build_llm(model=HAIKU_MODEL, max_tokens=1024, temperature=0.3)

    # Load optimized prompt from registry, fall back to hardcoded default
    active_prompt = get_active_prompt("discovery_search_query") or _SEARCH_QUERY_PROMPT
    prompt = active_prompt.format(
        num_queries=num_queries,
        keywords=", ".join(search_config.keywords),
        remote_only=search_config.remote_only,
        location=", ".join(search_config.locations) if search_config.locations else "Remote / United States",
    )

    from langchain_core.messages import HumanMessage
    response = await llm.ainvoke([HumanMessage(content=prompt)])

    try:
        raw = response.content
        if isinstance(raw, list):
            text = " ".join(
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in raw
            )
        else:
            text = str(raw) if raw else ""
        # Strip markdown code fences if present
        text = text.replace("```json", "").replace("```", "").strip()
        # Extract JSON array from response
        start = text.index("[")
        end = text.rindex("]") + 1
        queries = json.loads(text[start:end])
        if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
            return queries[:num_queries]
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Failed to parse LLM search queries (%s), using defaults", exc)

    # Fallback queries
    kw = search_config.keywords[0] if search_config.keywords else "Software Engineer"
    remote = "remote" if search_config.remote_only else ""
    return [
        f"{kw} {remote} site:boards.greenhouse.io",
        f"{kw} {remote} site:jobs.lever.co",
        f"{kw} {remote} site:jobs.ashbyhq.com",
        f"{kw} {remote} site:myworkdayjobs.com",
        f"{kw} {remote} site:jobs.smartrecruiters.com",
        f"{kw} {remote} apply now greenhouse OR lever 2026",
    ]


async def _parse_search_results(raw_results: str) -> List[Dict[str, Any]]:
    """Use LLM to parse raw search results into structured job data.

    Since MCP search returns JSON with an ``organic`` array, we first try
    direct JSON extraction before falling back to LLM parsing.
    """
    # --- Fast path: extract directly from structured JSON results ---
    jobs_direct: List[Dict[str, Any]] = []
    for chunk in raw_results.split("\n---\n"):
        try:
            data = json.loads(chunk.strip())
            for item in data.get("organic", []):
                url = item.get("link", "")
                title_raw = item.get("title", "")
                desc = item.get("description", "")
                if url and title_raw:
                    jobs_direct.append({
                        "title": title_raw,
                        "company": "",  # will be enriched below
                        "location": "",
                        "url": url,
                        "salary": None,
                        "description": desc[:200],
                        "is_remote": "remote" in (title_raw + desc).lower(),
                    })
        except (json.JSONDecodeError, AttributeError):
            pass  # non-JSON chunk, skip

    if jobs_direct:
        # Try to extract company from title (common patterns: "Title - Company" or "Title | Company")
        for job in jobs_direct:
            title = job["title"]
            for sep in [" - ", " | ", " — ", " at "]:
                if sep in title:
                    parts = title.rsplit(sep, 1)
                    job["title"] = parts[0].strip()
                    job["company"] = parts[1].strip().removeprefix("Careers @ ").removeprefix("Jobs at ")
                    break
            if not job["company"]:
                # Extract company from greenhouse URL pattern: /boards.greenhouse.io/{company}/
                import re
                m = re.search(r'greenhouse\.io/(\w+)/', job["url"])
                if m:
                    job["company"] = m.group(1).replace("-", " ").title()
        logger.info("Direct JSON extraction: %d jobs from search results", len(jobs_direct))
        return jobs_direct

    # --- Slow path: use LLM for unstructured results ---
    llm = build_llm(model=HAIKU_MODEL, max_tokens=4096, temperature=0.0)
    prompt = _PARSE_RESULTS_PROMPT.format(results=raw_results[:15000])

    from langchain_core.messages import HumanMessage
    response = await llm.ainvoke([HumanMessage(content=prompt)])

    try:
        text = response.content if isinstance(response.content, str) else str(response.content)
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.index("[")
        end = text.rindex("]") + 1
        jobs = json.loads(text[start:end])
        if isinstance(jobs, list):
            return jobs
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Failed to parse LLM job results: %s — response preview: %s",
                       exc, (text[:300] if text else "empty"))

    return []


async def _mcp_discover(
    search_config: SearchConfig,
    session_id: str,
    max_results: int = 20,
) -> List[JobListing]:
    """Discover jobs using Bright Data MCP search + LLM parsing."""

    await emit_agent_event(session_id, "discovery_progress", {
        "board": "mcp",
        "step": "Generating smart search queries...",
    })

    # 1. Generate search queries
    queries = await _generate_search_queries(search_config)
    logger.info("MCP discovery: generated %d search queries", len(queries))

    # 2. Run searches via MCP
    await emit_agent_event(session_id, "discovery_progress", {
        "board": "mcp",
        "step": f"Searching {len(queries)} ATS platforms for matching jobs...",
    })

    all_results = []
    async with mcp_session() as session:
        for i, query in enumerate(queries):
            try:
                result = await mcp_search(session, query)
                all_results.append(result)
                logger.info("MCP search %d/%d: %d chars", i + 1, len(queries), len(result))
            except Exception:
                logger.warning("MCP search failed for query: %s", query, exc_info=True)

    if not all_results:
        logger.error("MCP discovery: all searches failed")
        return []

    combined_results = "\n---\n".join(all_results)

    # 3. Parse results with LLM
    await emit_agent_event(session_id, "discovery_progress", {
        "board": "mcp",
        "step": "Parsing job listings from search results...",
    })

    parsed_jobs = await _parse_search_results(combined_results)
    logger.info("MCP discovery: parsed %d jobs from search results", len(parsed_jobs))

    # 4. Convert to JobListing objects, filtering to ATS URLs only
    listings: List[JobListing] = []
    seen_urls: set = set()

    for raw in parsed_jobs:
        url = raw.get("url", "")
        if not url or not _is_ats_url(url):
            continue
        if _is_board_url(url):
            continue

        # Deduplicate by URL
        url_key = url.lower().split("?")[0]
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)

        title = raw.get("title", "").strip()
        company = raw.get("company", "").strip()
        if not title or not company:
            continue

        location = raw.get("location", "Remote").strip()
        is_remote = raw.get("is_remote", False) or "remote" in location.lower()

        listing = JobListing(
            id=str(uuid4()),
            title=title,
            company=company,
            location=location,
            url=url.strip(),
            board=JobBoard.GOOGLE_JOBS,  # sourced externally (not a specific board)
            ats_type=_detect_ats_type(url),
            salary_range=raw.get("salary"),
            description_snippet=raw.get("description", "")[:500] or None,
            is_remote=is_remote,
            discovered_at=datetime.utcnow(),
        )
        listings.append(listing)

        if len(listings) >= max_results:
            break

    await emit_agent_event(session_id, "discovery_progress", {
        "board": "mcp",
        "step": f"Found {len(listings)} jobs on ATS platforms via search",
        "count": len(listings),
    })

    logger.info("MCP discovery: %d valid ATS listings", len(listings))
    return listings


async def discover_all_boards(
    boards: List[str],
    search_config: SearchConfig,
    session_id: str,
    max_per_board: int = 20,
) -> List[JobListing]:
    """Discover jobs using Bright Data MCP + Greenhouse API.

    Drop-in replacement for direct_discovery.discover_all_boards().
    Same signature, same return type.

    The ``boards`` parameter is accepted for interface compatibility but
    is effectively ignored -- MCP searches across all ATS platforms
    simultaneously rather than per-board.
    """
    all_jobs: List[JobListing] = []
    total_max = max_per_board * max(len(boards), 3)

    # Run MCP search and Greenhouse API in parallel
    greenhouse_task = _greenhouse_discover(search_config, session_id, max_per_board)
    mcp_task = _mcp_discover(search_config, session_id, total_max)

    results = await asyncio.gather(greenhouse_task, mcp_task, return_exceptions=True)

    for label, result in zip(["greenhouse", "mcp"], results):
        if isinstance(result, Exception):
            logger.error("%s discovery failed: %s", label, result)
            await emit_agent_event(session_id, "discovery_progress", {
                "board": label,
                "step": f"{label.title()} failed: {str(result)[:80]}",
                "error": True,
            })
        elif result:
            all_jobs.extend(result)

    # Deduplicate across sources (by title + company)
    seen: set = set()
    deduped: List[JobListing] = []
    for job in all_jobs:
        key = f"{job.title.lower().strip()}|{job.company.lower().strip()}"
        if key not in seen:
            seen.add(key)
            deduped.append(job)

    await emit_agent_event(session_id, "discovery_progress", {
        "board": "all",
        "step": f"Discovery complete: {len(deduped)} jobs found",
        "count": len(deduped),
        "progress": 100,
    })

    logger.info("Total discovery: %d raw -> %d deduped jobs", len(all_jobs), len(deduped))
    return deduped


async def _greenhouse_discover(
    search_config: SearchConfig,
    session_id: str,
    max_results: int,
) -> List[JobListing]:
    """Run the Greenhouse API scraper (free, no browser needed)."""
    await emit_agent_event(session_id, "discovery_progress", {
        "board": "greenhouse",
        "step": "Searching Greenhouse API (50 top tech companies)...",
    })

    try:
        from backend.browser.tools.job_boards.greenhouse_boards import (
            scrape_greenhouse_lever,
        )
        # context param is unused by the Greenhouse API scraper
        jobs = await scrape_greenhouse_lever(
            context=None,
            search_config=search_config,
            max_results=max_results * 3,  # collect broadly
        )

        await emit_agent_event(session_id, "discovery_progress", {
            "board": "greenhouse",
            "step": f"Found {len(jobs)} jobs on Greenhouse",
            "count": len(jobs),
        })

        logger.info("Greenhouse API: %d jobs", len(jobs))
        return jobs
    except Exception:
        logger.warning("Greenhouse API discovery failed", exc_info=True)
        return []
