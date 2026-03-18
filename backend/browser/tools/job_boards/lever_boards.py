# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Lever board scraper -- discovers jobs via Lever's public Postings API.

Lever provides a free, public API at api.lever.co/v0/postings/{company}
that returns all open postings for a company. No auth, no browser needed.

Jobs discovered here are guaranteed current (the API only returns active
postings) and can be submitted via the Lever API applier with zero CAPTCHA.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any, Dict, List

import aiohttp

from backend.shared.models.schemas import ATSType, JobBoard, JobListing, SearchConfig

logger = logging.getLogger(__name__)

# Lever public API
_LEVER_API = "https://api.lever.co/v0/postings/{company}"

# Curated list of tech companies on Lever with active job boards.
# These are verified to have open jobs as of 2026-03.
# The slug is the company identifier in the Lever URL.
_LEVER_COMPANIES = [
    # Big tech / unicorns
    "spotify",
    "netflix",
    "twitch",
    "snap",
    "reddit",
    "dropbox",
    "netlify",
    "cloudflare",
    "airtable",
    # AI / ML
    "openai",
    "scaleai",
    "huggingface",
    "runway",
    "stability",
    "midjourney",
    "character",
    "jasper",
    "covariant",
    "adept",
    "inflection",
    "deepgram",
    "assemblyai",
    "replicate",
    "weights-and-biases",
    # Fintech
    "mercury",
    "rippling",
    "carta",
    "pipe",
    "marqeta",
    "column",
    # Dev tools / infra
    "vercel",
    "supabase",
    "railway",
    "render",
    "pulumi",
    "temporal",
    "prefect",
    "dagster",
    "airbyte",
    "gitpod",
    "sourcegraph",
    "grafana",
    "clickhouse",
    "cockroachlabs",
    "planetscale",
    "neon",
    "turso",
    "convex",
    # Security
    "snyk",
    "lacework",
    "orca-security",
    "semgrep",
    # Growth / SaaS
    "notion",
    "figma",
    "loom",
    "miro",
    "calendly",
    "zapier",
    "webflow",
    "retool",
    "amplitude",
    "mixpanel",
    "segment",
    "braze",
    "contentful",
    "prismic",
    "sanity",
    # Health / biotech
    "color",
    "ro",
    "noom",
    "hims",
    # Other notable
    "anduril",
    "palantir",
    "flexport",
    "aircall",
    "vanta",
    "drata",
    "launchdarkly",
    "split",
    "flagsmith",
    "posthog",
    "rudderstack",
]


async def _fetch_company_postings(
    session: aiohttp.ClientSession,
    company: str,
) -> List[Dict]:
    """Fetch all open postings for a single company from Lever API."""
    url = _LEVER_API.format(company=company)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            if isinstance(data, list):
                return data
            return []
    except Exception:
        logger.debug("Failed to fetch Lever postings for %s", company)
        return []


def _normalize(text: str) -> str:
    """Normalize text for flexible matching (full-stack == fullstack, etc.)."""
    return text.lower().replace("-", "").replace("–", "").replace("—", "")


def _matches_keywords(posting: Dict, keywords: List[str], remote_only: bool) -> bool:
    """Check if a Lever posting matches any of the search keywords."""
    title = (posting.get("text") or "").lower()
    title_norm = _normalize(title)

    # Location from categories
    categories = posting.get("categories", {})
    location = (categories.get("location") or "").lower()
    commitment = (categories.get("commitment") or "").lower()
    team = (categories.get("team") or "").lower()

    # Remote filter
    if remote_only:
        is_remote = any(
            t in f"{location} {title} {commitment}"
            for t in ["remote", "anywhere", "distributed"]
        )
        if not is_remote:
            return False

    # Keyword match — flexible: normalize hyphens, match any keyword
    for kw in keywords:
        words = _normalize(kw).split()
        if all(w in title_norm for w in words):
            return True

    # Also match on team/department for broader coverage
    # e.g. keyword "engineer" matches team "Engineering"
    team_norm = _normalize(f"{team} {commitment}")
    for kw in keywords:
        core_words = [w for w in _normalize(kw).split() if len(w) > 3]
        if core_words and any(w in title_norm or w in team_norm for w in core_words):
            # At least one significant keyword word appears in title or team
            # AND the title looks like an engineering role
            eng_indicators = ["engineer", "developer", "architect", "fullstack",
                              "frontend", "backend", "software", "sre", "devops",
                              "platform", "infrastructure", "ml", "ai", "data"]
            if any(ind in title_norm for ind in eng_indicators):
                return True

    return False


async def scrape_lever(
    search_config: SearchConfig,
    *,
    max_results: int = 20,
) -> List[JobListing]:
    """Discover jobs from Lever's public Postings API.

    Returns guaranteed-current postings that can be submitted via the
    Lever API applier (no CAPTCHA, no browser needed).
    """
    keywords = search_config.keywords or ["software engineer"]
    remote_only = search_config.remote_only
    all_listings: List[JobListing] = []

    logger.info(
        "Lever API discovery starting — %d companies, keywords=%s, remote=%s",
        len(_LEVER_COMPANIES), keywords, remote_only,
    )

    async with aiohttp.ClientSession(
        headers={"User-Agent": "Mozilla/5.0 JobHunter/1.0"},
    ) as session:
        # Fetch all companies in parallel
        tasks = [
            _fetch_company_postings(session, company)
            for company in _LEVER_COMPANIES
        ]
        results = await asyncio.gather(*tasks)

        # Spread across companies
        max_per_company = max(3, max_results // 8)

        for company_slug, postings in zip(_LEVER_COMPANIES, results):
            company_count = 0
            for posting in postings:
                if len(all_listings) >= max_results:
                    break
                if company_count >= max_per_company:
                    break

                if not _matches_keywords(posting, keywords, remote_only):
                    continue

                title = posting.get("text", "Unknown")
                posting_id = posting.get("id", "")
                if not posting_id:
                    continue

                # Build the apply URL
                apply_url = f"https://jobs.lever.co/{company_slug}/{posting_id}"

                # Extract company name from posting or slug
                categories = posting.get("categories", {})
                location = categories.get("location") or "Unknown"

                is_remote = any(
                    t in location.lower() for t in ["remote", "anywhere"]
                )

                # Dedup
                key = f"{title.lower()}|{company_slug.lower()}"
                existing = {f"{l.title.lower()}|{l.company.lower()}" for l in all_listings}
                if key in existing:
                    continue

                job_id = hashlib.sha256(apply_url.encode()).hexdigest()[:16]
                listing = JobListing(
                    id=job_id,
                    title=title,
                    company=company_slug.replace("-", " ").title(),
                    location=location,
                    url=apply_url,
                    board=JobBoard.GOOGLE_JOBS,
                    ats_type=ATSType.LEVER,
                    is_remote=is_remote,
                    is_easy_apply=True,  # Lever API = no browser needed
                )
                all_listings.append(listing)
                company_count += 1

            if len(all_listings) >= max_results:
                break

    logger.info("Lever API discovery found %d listings", len(all_listings))
    return all_listings
