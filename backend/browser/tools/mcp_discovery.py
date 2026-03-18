# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Search-based agentic discovery -- uses Serper (Google Search API) to find jobs.

Instead of scraping LinkedIn/Indeed/Glassdoor (auth-walled), searches for jobs
directly on ATS platforms (Greenhouse, Lever, Ashby, Workday, etc.) using
Serper's Google Search API with site: operators.

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
import hashlib
from uuid import uuid4

from backend.browser.tools.serper_client import serper_search
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

PRIORITIZE these ATS sites (ordered by application success rate):
- jobs.lever.co (HIGHEST PRIORITY — generate at least 4 queries for Lever)
- jobs.ashbyhq.com (HIGH PRIORITY — generate at least 3 queries for Ashby)
- boards.greenhouse.io (generate 1 query only — reCAPTCHA blocks most submissions)
- myworkdayjobs.com (generate 0-1 queries — auth walls block submissions)

Job criteria:
- Keywords: {keywords}
- Remote only: {remote_only}
- Location: {location}
{exclusion_block}
{round_block}
Generate queries using site: operators. Each query MUST include at least one \
of the exact keywords above — do NOT broaden or substitute with related terms. \
Each query should target a different ATS platform. \
Focus on finding CURRENT job postings (2026).

Return a JSON array of query strings, nothing else. Example:
["Full stack engineer remote site:jobs.lever.co", "AI engineer site:jobs.ashbyhq.com 2026", "software engineer site:jobs.lever.co"]
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
    applied_companies: set[str] | None = None,
    round_number: int = 0,
) -> List[str]:
    """Use LLM to generate smart search queries targeting ATS sites."""
    temperature = 0.9 if round_number > 0 else 0.7
    llm = build_llm(model=HAIKU_MODEL, max_tokens=1024, temperature=temperature)

    # Build exclusion and round-awareness blocks
    exclusion_block = ""
    if applied_companies:
        top_companies = sorted(applied_companies)[:20]
        exclusion_block = (
            f"AVOID these companies (already applied): {', '.join(top_companies)}\n"
            "Focus on companies NOT in this list."
        )

    round_block = ""
    if round_number > 0:
        round_block = (
            f"This is search round {round_number + 1}. Generate DIFFERENT queries than a standard search. "
            "Try alternative keyword phrasings, different ATS site combinations, "
            "less common job title variations, and different company sizes/stages."
        )

    # Load optimized prompt from registry, fall back to hardcoded default
    active_prompt = get_active_prompt("discovery_search_query") or _SEARCH_QUERY_PROMPT
    prompt = active_prompt.format(
        num_queries=num_queries,
        keywords=", ".join(search_config.keywords),
        remote_only=search_config.remote_only,
        location=", ".join(search_config.locations) if search_config.locations else "Remote / United States",
        exclusion_block=exclusion_block,
        round_block=round_block,
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

    # Fallback queries — prioritize Lever and Ashby (no reCAPTCHA)
    kw = search_config.keywords[0] if search_config.keywords else "Software Engineer"
    remote = " remote" if search_config.remote_only else ""
    return [
        f"{kw}{remote} site:jobs.lever.co",
        f"{kw}{remote} site:jobs.lever.co 2026",
        f"{kw}{remote} site:jobs.ashbyhq.com",
        f"{kw}{remote} site:jobs.ashbyhq.com 2026",
        f"{kw}{remote} site:boards.greenhouse.io",
        f"{kw}{remote} apply now lever OR ashby 2026",
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
        import re

        _ROLE_WORDS = {"engineer", "developer", "designer", "manager", "analyst",
                       "scientist", "architect", "lead", "director", "specialist",
                       "fullstack", "full-stack", "backend", "frontend", "devops",
                       "sre", "intern", "coordinator", "consultant", "associate",
                       "senior", "junior", "staff", "principal", "software",
                       "data", "full", "stack", "node", "remote", "python",
                       "react", "java", "golang", "rust", "applied"}

        def _looks_like_role(text: str) -> bool:
            """Return True if *text* looks like a job title rather than a company."""
            words = set(text.lower().split())
            return bool(words & _ROLE_WORDS)

        # Try to extract company from title (common patterns: "Title - Company" or "Title | Company")
        # Prefer " | " over " - " since pipes are more commonly the title/company delimiter
        # in Google search results (Lever uses "Title | Company", Greenhouse uses "Title - Company")
        for job in jobs_direct:
            title = job["title"]
            for sep in [" | ", " - ", " — ", " at "]:
                if sep in title:
                    parts = title.rsplit(sep, 1)
                    left, right = parts[0].strip(), parts[1].strip().removeprefix("Careers @ ").removeprefix("Jobs at ")
                    left_is_role = _looks_like_role(left)
                    right_is_role = _looks_like_role(right)
                    # Case 1: left is a number/ID (e.g. "1008 - Senior Fullstack Engineer")
                    # or left is company name and right is role → swap
                    if left.isdigit() or (not left_is_role and right_is_role):
                        job["title"] = right
                        job["company"] = left if not left.isdigit() else ""
                        break
                    # Case 2: normal "Title - Company" pattern
                    job["title"] = left
                    job["company"] = right
                    break
            if not job["company"]:
                # Extract company from greenhouse/ashby URL patterns
                m = re.search(r'(?:greenhouse\.io|jobs\.ashbyhq\.com)/(\w[\w-]*)/', job["url"])
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
    applied_companies: set[str] | None = None,
    applied_urls: set[str] | None = None,
    round_number: int = 0,
) -> List[JobListing]:
    """Discover jobs using Serper Google Search + LLM parsing."""

    await emit_agent_event(session_id, "discovery_progress", {
        "board": "search",
        "step": "Generating smart search queries...",
    })

    # 1. Generate search queries (with exclusion context for re-runs)
    queries = await _generate_search_queries(
        search_config,
        applied_companies=applied_companies,
        round_number=round_number,
    )
    logger.info("Serper discovery: generated %d search queries (round %d)", len(queries), round_number)

    # 2. Run searches via Serper (all queries in parallel)
    # Broader time window on subsequent rounds; more results per query
    tbs = "qdr:m" if round_number > 0 else "qdr:w"
    num_results = 20  # Serper max is 20 per request

    await emit_agent_event(session_id, "discovery_progress", {
        "board": "search",
        "step": f"Searching {len(queries)} ATS platforms for matching jobs...",
    })

    async def _safe_search(query: str, page: int = 1) -> Optional[str]:
        try:
            return await serper_search(query, num_results=num_results, tbs=tbs, page=page)
        except Exception:
            logger.warning("Serper search failed for query: %s (page %d)", query, page, exc_info=True)
            return None

    results = await asyncio.gather(*[_safe_search(q) for q in queries])
    all_results = [r for r in results if r is not None]

    if not all_results:
        logger.error("Serper discovery: all searches failed")
        return []

    combined_results = "\n---\n".join(all_results)

    # 3. Parse results with LLM
    await emit_agent_event(session_id, "discovery_progress", {
        "board": "search",
        "step": "Parsing job listings from search results...",
    })

    parsed_jobs = await _parse_search_results(combined_results)
    logger.info("Serper discovery: parsed %d jobs from search results", len(parsed_jobs))

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

        # Skip generic page titles that aren't actual job listings
        _GENERIC_TITLES = {
            "careers", "jobs", "open positions", "openings", "job openings",
            "work with us", "join us", "join our team", "career opportunities",
            "job application", "apply",
        }
        if title.lower() in _GENERIC_TITLES:
            logger.debug("Skipping generic title '%s' from %s", title, url)
            continue

        # Skip titles that are just numbers (IDs, not real job titles)
        if title.isdigit():
            logger.debug("Skipping numeric title '%s' from %s", title, url)
            continue

        # Clean common ATS title prefixes
        for prefix in ["Job Application for ", "Apply for "]:
            if title.startswith(prefix):
                title = title[len(prefix):]

        # If company is a location string (e.g. "(Remote)"), try to extract
        # real company from URL, otherwise skip
        _LOCATION_COMPANIES = {"remote", "(remote)", "remote)", "worldwide", "global"}
        if company.lower().strip("() ") in _LOCATION_COMPANIES or company.startswith("("):
            import re as _re
            m = _re.search(r'(?:greenhouse\.io|jobs\.ashbyhq\.com|jobs\.lever\.co)/(\w[\w-]*)/', url)
            if m:
                company = m.group(1).replace("-", " ").title()
            else:
                logger.debug("Skipping job with location-as-company '%s': %s", company, url)
                continue

        location = raw.get("location", "Remote").strip()
        is_remote = raw.get("is_remote", False) or "remote" in location.lower()

        # Deterministic ID from URL so cross-session dedup works
        job_id = hashlib.sha256(url.strip().encode()).hexdigest()[:16]
        listing = JobListing(
            id=job_id,
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

    # If too few new listings after filtering applied URLs, try page 2
    _applied = applied_urls or set()
    new_count = sum(1 for j in listings if j.url not in _applied)
    if new_count < 15 and queries:
        logger.info("Serper discovery: only %d new jobs after filter, fetching page 2", new_count)
        await emit_agent_event(session_id, "discovery_progress", {
            "board": "search",
            "step": f"Only {new_count} new jobs found, searching deeper...",
        })
        p2_results = await asyncio.gather(*[_safe_search(q, page=2) for q in queries])
        p2_valid = [r for r in p2_results if r is not None]
        if p2_valid:
            p2_combined = "\n---\n".join(p2_valid)
            p2_parsed = await _parse_search_results(p2_combined)
            for raw in p2_parsed:
                url = raw.get("url", "")
                if not url or not _is_ats_url(url) or _is_board_url(url):
                    continue
                url_key = url.lower().split("?")[0]
                if url_key in seen_urls:
                    continue
                seen_urls.add(url_key)
                title = raw.get("title", "").strip()
                company = raw.get("company", "").strip()
                if not title or not company or title.lower() in _GENERIC_TITLES or title.isdigit():
                    continue
                for prefix in ["Job Application for ", "Apply for "]:
                    if title.startswith(prefix):
                        title = title[len(prefix):]
                location = raw.get("location", "Remote").strip()
                is_remote = raw.get("is_remote", False) or "remote" in location.lower()
                job_id = hashlib.sha256(url.strip().encode()).hexdigest()[:16]
                listings.append(JobListing(
                    id=job_id, title=title, company=company, location=location,
                    url=url.strip(), board=JobBoard.GOOGLE_JOBS,
                    ats_type=_detect_ats_type(url),
                    salary_range=raw.get("salary"),
                    description_snippet=raw.get("description", "")[:500] or None,
                    is_remote=is_remote, discovered_at=datetime.utcnow(),
                ))
            logger.info("Serper discovery: %d total after page 2", len(listings))

    await emit_agent_event(session_id, "discovery_progress", {
        "board": "search",
        "step": f"Found {len(listings)} jobs on ATS platforms via search",
        "count": len(listings),
    })

    logger.info("Serper discovery: %d valid ATS listings", len(listings))
    return listings


async def discover_all_boards(
    boards: List[str],
    search_config: SearchConfig,
    session_id: str,
    max_per_board: int = 20,
    applied_companies: set[str] | None = None,
    applied_urls: set[str] | None = None,
    round_number: int = 0,
) -> List[JobListing]:
    """Discover jobs using Serper Google Search + Greenhouse API.

    Drop-in replacement for direct_discovery.discover_all_boards().
    Same signature, same return type.

    The ``boards`` parameter is accepted for interface compatibility but
    is effectively ignored -- Serper searches across all ATS platforms
    simultaneously rather than per-board.
    """
    all_jobs: List[JobListing] = []
    total_max = max_per_board * max(len(boards), 3)

    # Run Lever API, Greenhouse API, and Serper search in parallel.
    # Lever API is highest priority — guaranteed current, no CAPTCHA.
    lever_task = _lever_discover(search_config, session_id, max_per_board)
    greenhouse_task = _greenhouse_discover(search_config, session_id, max_per_board)
    mcp_task = _mcp_discover(
        search_config, session_id, total_max,
        applied_companies=applied_companies,
        applied_urls=applied_urls,
        round_number=round_number,
    )

    results = await asyncio.gather(lever_task, greenhouse_task, mcp_task, return_exceptions=True)

    # Priority order: Lever API > Serper (Lever/Ashby) > Greenhouse API.
    # Lever API jobs are guaranteed current and submittable.
    lever_jobs: List[JobListing] = []
    serper_jobs: List[JobListing] = []
    greenhouse_jobs: List[JobListing] = []
    for label, result in zip(["lever", "greenhouse", "search"], results):
        if isinstance(result, Exception):
            logger.error("%s discovery failed: %s", label, result)
            await emit_agent_event(session_id, "discovery_progress", {
                "board": label,
                "step": f"{label.title()} failed: {str(result)[:80]}",
                "error": True,
            })
        elif result:
            if label == "lever":
                lever_jobs.extend(result)
            elif label == "search":
                serper_jobs.extend(result)
            else:
                greenhouse_jobs.extend(result)

    # Greenhouse reCAPTCHA is solvable via 2captcha — prioritize Greenhouse.
    # Lever/Ashby use hCaptcha which we can't solve yet.
    # Put Greenhouse first so those jobs rank higher in dedup.
    all_jobs = greenhouse_jobs + lever_jobs + serper_jobs
    logger.info("Discovery sources: %d Lever API, %d Serper, %d Greenhouse API",
                len(lever_jobs), len(serper_jobs), len(greenhouse_jobs))

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


async def _lever_discover(
    search_config: SearchConfig,
    session_id: str,
    max_results: int,
) -> List[JobListing]:
    """Run the Lever API scraper (free, no browser, no CAPTCHA)."""
    await emit_agent_event(session_id, "discovery_progress", {
        "board": "lever",
        "step": "Searching Lever API (80+ tech companies)...",
    })

    try:
        from backend.browser.tools.job_boards.lever_boards import scrape_lever
        jobs = await scrape_lever(
            search_config=search_config,
            max_results=max_results * 3,
        )

        await emit_agent_event(session_id, "discovery_progress", {
            "board": "lever",
            "step": f"Found {len(jobs)} jobs on Lever (guaranteed current)",
            "count": len(jobs),
        })

        logger.info("Lever API: %d jobs (all current, submittable)", len(jobs))
        return jobs
    except Exception:
        logger.warning("Lever API discovery failed", exc_info=True)
        return []


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
