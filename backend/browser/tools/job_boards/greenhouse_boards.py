# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Greenhouse board scraper -- discovers jobs via Greenhouse's public JSON API.

Greenhouse provides a free, public API at boards-api.greenhouse.io that returns
all open jobs for a company. No auth, no browser, no scraping required.

We maintain a curated list of tech companies that use Greenhouse, then filter
their job listings by keyword match.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
import hashlib
from uuid import uuid4

import aiohttp

from backend.shared.models.schemas import ATSType, JobBoard, JobListing, SearchConfig

logger = logging.getLogger(__name__)

# Greenhouse public API
_GH_API = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs"

# Curated list of tech companies on Greenhouse with active job boards.
# These are verified to have open jobs as of 2026-03.
# The slug is the company identifier in the Greenhouse URL.
_GREENHOUSE_COMPANIES = [
    "anthropic",
    "stripe",
    "figma",
    "databricks",
    "verkada",
    "relativity",
    "discord",
    "airbnb",
    "coinbase",
    "duolingo",
    "lyft",
    "affirm",
    "brex",
    "ramp",
    "plaid",
    "gusto",
    "airtable",
    "anduril",
    "palantir",
    "navan",
    "watershed",
    "hex",
    "replit",
    "cohere",
    "perplexityai",
    "mistral",
    "cerebras",
    "sambanova",
    "together",
    "langchain",
    "pinecone",
    "weaviate",
    "chroma",
    "huggingface",
    "modal",
    "dbt",
    "fivetran",
    "snowflake",
    "hashicorp",
    "vercel",
    "supabase",
    "netlify",
    "posthog",
    "linear",
    "loom",
    "miro",
    "canva",
    "retool",
]


async def _fetch_company_jobs(
    session: aiohttp.ClientSession,
    company: str,
) -> List[Dict]:
    """Fetch all jobs for a single company from Greenhouse API."""
    url = _GH_API.format(company=company)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            return data.get("jobs", [])
    except Exception:
        logger.debug("Failed to fetch Greenhouse jobs for %s", company)
        return []


def _matches_keywords(job: Dict, keywords: List[str], remote_only: bool) -> bool:
    """Check if a job matches any of the search keywords."""
    title = (job.get("title") or "").lower()
    location = (job.get("location", {}).get("name") or "").lower()

    # Remote filter — relaxed: skip only if location is clearly on-site only
    # Many Greenhouse listings omit "remote" from location even if they support it
    if remote_only:
        onsite_only_indicators = ["on-site only", "in-office only", "no remote"]
        if any(ind in location for ind in onsite_only_indicators):
            return False

    # Keyword match (match any keyword in title)
    lower_keywords = [kw.lower() for kw in keywords]
    for kw in lower_keywords:
        # Split multi-word keywords and check all words present
        words = kw.split()
        if all(w in title for w in words):
            return True

    return False


async def scrape_greenhouse_lever(
    context: Any,  # unused — we use API, not browser
    search_config: SearchConfig,
    *,
    max_results: int = 10,
) -> List[JobListing]:
    """Discover jobs from Greenhouse API.

    Parameters
    ----------
    context:
        Playwright BrowserContext (unused — kept for interface compatibility).
    search_config:
        Search keywords and filters.
    max_results:
        Max listings to return.
    """
    keywords = search_config.keywords or ["software engineer"]
    remote_only = search_config.remote_only
    all_listings: List[JobListing] = []

    logger.info(
        "Greenhouse API discovery starting — %d companies, keywords=%s, remote=%s",
        len(_GREENHOUSE_COMPANIES), keywords, remote_only,
    )

    async with aiohttp.ClientSession(
        headers={"User-Agent": "Mozilla/5.0 JobHunter/1.0"},
    ) as session:
        # Fetch all companies in parallel (fast — JSON API)
        tasks = [
            _fetch_company_jobs(session, company)
            for company in _GREENHOUSE_COMPANIES
        ]
        results = await asyncio.gather(*tasks)

        # Limit per company to spread across companies
        max_per_company = max(3, max_results // 8)

        for company_slug, jobs in zip(_GREENHOUSE_COMPANIES, results):
            company_count = 0
            for job in jobs:
                if len(all_listings) >= max_results:
                    break
                if company_count >= max_per_company:
                    break

                if not _matches_keywords(job, keywords, remote_only):
                    continue

                title = job.get("title", "Unknown")
                company_name = job.get("company_name", company_slug.title())
                location = job.get("location", {}).get("name", "Unknown")
                abs_url = job.get("absolute_url", "")

                if not abs_url:
                    continue

                # Only keep URLs that go directly to Greenhouse forms
                # (some companies like Stripe redirect to their own site)
                if "greenhouse.io" not in abs_url.lower():
                    continue

                # Dedup
                key = f"{title.lower()}|{company_name.lower()}"
                existing = {f"{l.title.lower()}|{l.company.lower()}" for l in all_listings}
                if key in existing:
                    continue

                is_remote = bool(
                    location and any(t in location.lower() for t in ["remote", "anywhere"])
                )

                # Deterministic ID from URL so cross-session dedup works
                job_id = hashlib.sha256(abs_url.encode()).hexdigest()[:16]
                listing = JobListing(
                    id=job_id,
                    title=title,
                    company=company_name,
                    location=location,
                    url=abs_url,
                    board=JobBoard.GOOGLE_JOBS,  # sourced externally
                    ats_type=ATSType.GREENHOUSE,
                    is_remote=is_remote,
                    is_easy_apply=False,
                )
                all_listings.append(listing)
                company_count += 1

            if len(all_listings) >= max_results:
                break

    logger.info("Greenhouse API discovery found %d listings", len(all_listings))
    return all_listings
