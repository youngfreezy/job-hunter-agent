# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Indeed job board scraper using Playwright browser automation.

Navigates to Indeed's search page, enters query parameters, and extracts
job listings from the results pages.  Returns partial results on failure
rather than raising, so the pipeline can continue with other boards.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.browser.anti_detect.stealth import apply_stealth
from backend.shared.models.schemas import ATSType, JobBoard, JobListing, SearchConfig

logger = logging.getLogger(__name__)

INDEED_BASE = "https://www.indeed.com"
INDEED_SEARCH = f"{INDEED_BASE}/jobs"

# Maximum pages to paginate through per search.
# Keep at 1 — page 1 returns ~15 results per keyword, and Bright Data's
# remote browser is slow (~10-20s per navigation). With 5 keywords that's
# already 50-100s. Pagination adds latency without enough extra value.
MAX_PAGES = 1

# Captcha / block selectors
_BLOCK_SELECTORS = [
    "#captcha-form",
    "#px-captcha",
    ".cf-challenge-running",
    "#challenge-running",
    ".g-recaptcha",
    "#recaptcha",
    'div[class*="captcha"]',
]


async def _is_blocked(page: Any) -> bool:
    """Return True if Indeed is showing a captcha or block page."""
    for sel in _BLOCK_SELECTORS:
        try:
            if await page.query_selector(sel):
                logger.warning("Indeed: block/captcha detected (selector: %s)", sel)
                return True
        except Exception:
            continue
    try:
        title = (await page.title() or "").lower()
        if any(kw in title for kw in ("captcha", "blocked", "denied", "robot", "just a moment")):
            logger.warning("Indeed: block detected via page title '%s'", title)
            return True
    except Exception:
        pass
    return False


async def scrape_indeed(
    context: Any,  # BrowserContext
    search_config: SearchConfig,
    *,
    max_results: int = 15,
) -> List[JobListing]:
    """Scrape Indeed for job listings matching *search_config*.

    Parameters
    ----------
    context:
        An isolated Playwright BrowserContext (with stealth already configured).
    search_config:
        The structured search configuration from the Intake agent.
    max_results:
        Maximum number of listings to return.

    Returns
    -------
    list[JobListing]
        Discovered job listings from Indeed.  May return fewer than
        *max_results* if blocked or if there are insufficient results.
    """
    page = await context.new_page()
    await apply_stealth(page)
    listings: List[JobListing] = []

    try:
        location = search_config.locations[0] if search_config.locations else ""
        queries = search_config.keywords[:5] if search_config.keywords else ["software engineer"]

        base_params: Dict[str, str] = {}
        if search_config.remote_only:
            base_params["remotejob"] = "032b3046-06a3-4876-8dfd-474eb5e7ed11"
        elif location and location.lower() != "remote":
            base_params["l"] = location
            base_params["radius"] = str(search_config.search_radius)
        if search_config.salary_min:
            base_params["salary"] = str(search_config.salary_min)

        for query in queries:
            if len(listings) >= max_results:
                break

            params = {**base_params, "q": query}
            param_str = "&".join(f"{k}={v}" for k, v in params.items())
            search_url = f"{INDEED_SEARCH}?{param_str}"

            logger.info("Indeed scraper navigating to: %s", search_url)

            for page_num in range(MAX_PAGES):
                if len(listings) >= max_results:
                    break

                url = search_url if page_num == 0 else f"{search_url}&start={page_num * 10}"
                await page.goto(url, wait_until="domcontentloaded", timeout=90000)
                # Extra wait for Bright Data CAPTCHA solving
                await page.wait_for_timeout(random.randint(3000, 6000))

                # Bright Data auto-solves CAPTCHAs — retry block check
                blocked = await _is_blocked(page)
                if blocked:
                    for retry in range(3):
                        logger.info("Indeed: waiting for CAPTCHA solve (attempt %d/3)...", retry + 1)
                        await page.wait_for_timeout(10000)
                        blocked = await _is_blocked(page)
                        if not blocked:
                            break
                if blocked:
                    logger.warning("Indeed: blocked on page %d -- returning %d partial results", page_num + 1, len(listings))
                    # Return partial results immediately instead of trying more keywords
                    return listings

                try:
                    await page.wait_for_selector(
                        'div.job_seen_beacon, div[class*="jobsearch-ResultsList"] li',
                        timeout=20000,
                    )
                except Exception:
                    logger.warning("Indeed: no job cards found on page %d (query: %s)", page_num + 1, query)
                    break

                cards = await page.query_selector_all(
                    'div.job_seen_beacon, div[class*="cardOutline"], td.resultContent'
                )

                for card in cards:
                    if len(listings) >= max_results:
                        break
                    try:
                        listing = await _parse_indeed_card(card, page)
                        if listing:
                            listings.append(listing)
                    except Exception:
                        logger.debug("Failed to parse an Indeed card", exc_info=True)

                if page_num < MAX_PAGES - 1:
                    await page.wait_for_timeout(random.randint(2000, 5000))

        logger.info("Indeed scraper found %d listings", len(listings))

    except Exception:
        logger.exception("Indeed scraper failed -- returning %d partial results", len(listings))
    finally:
        await page.close()

    return listings


async def _parse_indeed_card(
    card: Any,  # ElementHandle
    page: Any,
) -> Optional[JobListing]:
    """Parse a single Indeed job card into a JobListing."""

    # Title
    title_el = await card.query_selector(
        'h2.jobTitle a span[title], h2.jobTitle span, a[data-jk] span'
    )
    title = (await title_el.inner_text()).strip() if title_el else None
    if not title:
        return None

    # Company
    company_el = await card.query_selector(
        'span[data-testid="company-name"], span.companyName, span.company'
    )
    company = (await company_el.inner_text()).strip() if company_el else "Unknown"

    # Location
    location_el = await card.query_selector(
        'div[data-testid="text-location"], div.companyLocation'
    )
    location = (await location_el.inner_text()).strip() if location_el else "Unknown"

    # URL -- look for the job link
    link_el = await card.query_selector('h2.jobTitle a, a[data-jk]')
    href = await link_el.get_attribute("href") if link_el else None
    if href and not href.startswith("http"):
        href = f"{INDEED_BASE}{href}"
    url = href or f"{INDEED_BASE}/viewjob?jk={uuid4().hex[:12]}"

    # Salary (optional)
    salary_el = await card.query_selector(
        'div[class*="salary-snippet"], div.metadata.salary-snippet-container span'
    )
    salary_range = (await salary_el.inner_text()).strip() if salary_el else None

    # Snippet
    snippet_el = await card.query_selector(
        'div.job-snippet, div[class*="job-snippet"], td.snip'
    )
    snippet = (await snippet_el.inner_text()).strip() if snippet_el else None

    # Date
    date_el = await card.query_selector('span.date, span[class*="date"]')
    posted_date = (await date_el.inner_text()).strip() if date_el else None

    # Remote detection
    is_remote = bool(location and "remote" in location.lower())

    # Easy apply badge
    easy_apply_el = await card.query_selector(
        'span[class*="easily-apply"], span.iaLabel'
    )
    is_easy_apply = easy_apply_el is not None

    return JobListing(
        id=str(uuid4()),
        title=title,
        company=company,
        location=location,
        url=url,
        board=JobBoard.INDEED,
        ats_type=ATSType.UNKNOWN,
        salary_range=salary_range,
        description_snippet=snippet,
        posted_date=posted_date,
        is_remote=is_remote,
        is_easy_apply=is_easy_apply,
    )
