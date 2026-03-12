# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""URL Hydrator -- converts raw job URLs into JobListing objects.

Given a list of user-provided job URLs, fetches each page and extracts
title, company, location, and ATS type from HTML metadata. No LLM needed.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from backend.shared.models.schemas import ATSType, JobBoard, JobListing

logger = logging.getLogger(__name__)

_TIMEOUT = 12.0

# Domain -> (ATSType, JobBoard)
_ATS_DOMAINS: dict[str, Tuple[ATSType, JobBoard]] = {
    "greenhouse.io": (ATSType.GREENHOUSE, JobBoard.OTHER),
    "lever.co": (ATSType.LEVER, JobBoard.OTHER),
    "ashbyhq.com": (ATSType.ASHBY, JobBoard.OTHER),
    "myworkdayjobs.com": (ATSType.WORKDAY, JobBoard.OTHER),
    "icims.com": (ATSType.ICIMS, JobBoard.OTHER),
    "linkedin.com": (ATSType.LINKEDIN, JobBoard.LINKEDIN),
    "indeed.com": (ATSType.UNKNOWN, JobBoard.INDEED),
    "glassdoor.com": (ATSType.UNKNOWN, JobBoard.GLASSDOOR),
    "ziprecruiter.com": (ATSType.UNKNOWN, JobBoard.ZIPRECRUITER),
}


def _detect_ats(url: str) -> Tuple[ATSType, JobBoard]:
    """Detect ATS type and board from URL domain."""
    host = urlparse(url).hostname or ""
    for domain, result in _ATS_DOMAINS.items():
        if domain in host:
            return result
    return ATSType.UNKNOWN, JobBoard.OTHER


def _extract_meta(html: str, name: str) -> Optional[str]:
    """Extract content from a <meta> tag by property or name."""
    # Try property= first (OpenGraph), then name=
    for attr in ("property", "name"):
        pattern = rf'<meta\s+{attr}="{name}"\s+content="([^"]*)"'
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        # Also match reversed attribute order
        pattern = rf'<meta\s+content="([^"]*)"\s+{attr}="{name}"'
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_title(html: str) -> str:
    """Extract <title> tag content."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _parse_title_company(raw_title: str) -> Tuple[str, str]:
    """Split a page title like 'Senior Engineer - Acme Corp' into (title, company).

    Common ATS title formats:
    - "Job Title - Company" (Greenhouse, Lever)
    - "Job Title at Company" (Ashby)
    - "Job Title | Company" (various)
    - "Company - Job Title" (some Workday)
    """
    # Try common separators
    for sep in [" - ", " at ", " @ ", " | ", " — ", " · "]:
        if sep in raw_title:
            parts = raw_title.split(sep, 1)
            # Heuristic: the shorter part is usually the company
            # But " at " almost always means title at company
            if sep in (" at ", " @ "):
                return parts[0].strip(), parts[1].strip()
            return parts[0].strip(), parts[1].strip()
    return raw_title, "Unknown"


async def hydrate_url(url: str, client: httpx.AsyncClient) -> JobListing:
    """Fetch a single URL and return a hydrated JobListing."""
    ats_type, board = _detect_ats(url)
    job_id = uuid4().hex[:12]

    try:
        resp = await client.get(
            url,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return JobListing(
            id=job_id,
            title="Unknown Position",
            company="Unknown",
            location="Unknown",
            url=url,
            board=board,
            ats_type=ats_type,
        )

    # Extract metadata
    og_title = _extract_meta(html, "og:title") or ""
    og_desc = _extract_meta(html, "og:description") or ""
    page_title = _extract_title(html)
    # Prefer <title> when it contains a separator (has company info)
    # og:title often only has the job title without company
    _seps = [" - ", " at ", " @ ", " | ", " — "]
    if page_title and any(s in page_title for s in _seps):
        raw_title = page_title
    else:
        raw_title = og_title or page_title

    title, company = _parse_title_company(raw_title)

    # Try to get company from og:site_name if we couldn't parse it
    if company == "Unknown":
        site_name = _extract_meta(html, "og:site_name")
        if site_name:
            company = site_name

    # Try to extract location from description or meta
    location = "Unknown"
    loc_meta = _extract_meta(html, "og:locale")
    if og_desc:
        # Many ATS descriptions include location like "Remote", "New York, NY", etc.
        loc_patterns = [
            r"(Remote)",
            r"(\w[\w\s]+,\s*[A-Z]{2})\b",  # "City, ST"
        ]
        for pat in loc_patterns:
            m = re.search(pat, og_desc)
            if m:
                location = m.group(1)
                break

    # Detect remote from content
    is_remote = bool(re.search(r"\bremote\b", (og_desc + " " + raw_title).lower()))

    logger.info(
        "Hydrated URL: %s -> title=%r, company=%r, ats=%s",
        url[:80], title, company, ats_type.value,
    )

    return JobListing(
        id=job_id,
        title=title or "Unknown Position",
        company=company or "Unknown",
        location=location,
        url=url,
        board=board,
        ats_type=ats_type,
        description_snippet=og_desc[:300] if og_desc else None,
        is_remote=is_remote,
    )


async def hydrate_urls(urls: List[str]) -> List[JobListing]:
    """Hydrate a list of URLs into JobListing objects concurrently."""
    if not urls:
        return []

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        import asyncio
        jobs = await asyncio.gather(*[hydrate_url(u.strip(), client) for u in urls if u.strip()])

    logger.info("Hydrated %d URLs into %d JobListings", len(urls), len(jobs))
    return list(jobs)
