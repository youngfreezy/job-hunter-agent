"""Glassdoor job board scraper using Playwright browser automation.

Glassdoor uses aggressive bot-detection (PerimeterX), so this scraper is
conservative with delays and returns partial results on blocks rather than
crashing the pipeline.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.browser.anti_detect.stealth import apply_stealth
from backend.shared.models.schemas import ATSType, JobBoard, JobListing, SearchConfig

logger = logging.getLogger(__name__)

GLASSDOOR_BASE = "https://www.glassdoor.com"
GLASSDOOR_JOBS = f"{GLASSDOOR_BASE}/Job"

MAX_PAGES = 1

# Captcha / block selectors
_BLOCK_SELECTORS = [
    "#px-captcha",
    "#captcha-form",
    ".cf-challenge-running",
    "#challenge-running",
    ".g-recaptcha",
    "#recaptcha",
    'div[class*="captcha"]',
    'iframe[src*="captcha"]',
]


async def _is_blocked(page: Any) -> bool:
    """Return True if Glassdoor is showing a captcha or block page."""
    for sel in _BLOCK_SELECTORS:
        try:
            if await page.query_selector(sel):
                logger.warning("Glassdoor: block/captcha detected (selector: %s)", sel)
                return True
        except Exception:
            continue
    try:
        title = (await page.title() or "").lower()
        if any(kw in title for kw in ("captcha", "blocked", "denied", "just a moment", "security")):
            logger.warning("Glassdoor: block detected via page title '%s'", title)
            return True
    except Exception:
        pass
    return False


async def scrape_glassdoor(
    context: Any,
    search_config: SearchConfig,
    *,
    max_results: int = 12,
) -> List[JobListing]:
    """Scrape Glassdoor for job listings matching *search_config*.

    Parameters
    ----------
    context:
        An isolated Playwright BrowserContext.
    search_config:
        Structured search configuration.
    max_results:
        Maximum listings to return.

    Returns
    -------
    list[JobListing]
        Discovered listings.  May return fewer than *max_results* if
        blocked or if there are insufficient results.
    """
    page = await context.new_page()
    await apply_stealth(page)
    listings: List[JobListing] = []

    try:
        location = search_config.locations[0] if search_config.locations else ""
        queries = search_config.keywords[:5] if search_config.keywords else ["software engineer"]

        base_params: Dict[str, str] = {}
        if search_config.remote_only:
            base_params["remoteWorkType"] = "1"
        elif location and location.lower() != "remote":
            base_params["locT"] = "C"
            base_params["locKeyword"] = location
            base_params["radius"] = "100"

        for query in queries:
            if len(listings) >= max_results:
                break

            params = {**base_params, "sc.keyword": query}
            param_str = "&".join(f"{k}={v}" for k, v in params.items())
            search_url = f"{GLASSDOOR_JOBS}/jobs.htm?{param_str}"

            logger.info("Glassdoor scraper navigating to: %s", search_url)

            for page_num in range(MAX_PAGES):
                if len(listings) >= max_results:
                    break

                url = search_url if page_num == 0 else f"{search_url}&p={page_num + 1}"
                await page.goto(url, wait_until="domcontentloaded", timeout=90000)
                # Extra wait for Bright Data CAPTCHA solving
                await page.wait_for_timeout(random.randint(5000, 8000))

                # Bright Data auto-solves CAPTCHAs — retry block check
                blocked = await _is_blocked(page)
                if blocked:
                    for retry in range(3):
                        logger.info("Glassdoor: waiting for CAPTCHA solve (attempt %d/3)...", retry + 1)
                        await page.wait_for_timeout(10000)
                        blocked = await _is_blocked(page)
                        if not blocked:
                            break
                if blocked:
                    logger.warning("Glassdoor: blocked on page %d -- returning %d partial results", page_num + 1, len(listings))
                    return listings

                try:
                    await page.wait_for_selector(
                        'li.react-job-listing, li[data-test="jobListing"], div.JobCard_jobCardContainer',
                        timeout=20000,
                    )
                except Exception:
                    logger.warning("Glassdoor: no job cards on page %d (query: %s)", page_num + 1, query)
                    break

                cards = await page.query_selector_all(
                    'li.react-job-listing, li[data-test="jobListing"], div.JobCard_jobCardContainer'
                )

                for card in cards:
                    if len(listings) >= max_results:
                        break
                    try:
                        listing = await _parse_glassdoor_card(card)
                        if listing:
                            listings.append(listing)
                    except Exception:
                        logger.debug("Failed to parse a Glassdoor card", exc_info=True)

                if page_num < MAX_PAGES - 1:
                    await page.wait_for_timeout(random.randint(3000, 5000))

        logger.info("Glassdoor scraper found %d listings", len(listings))

    except Exception:
        logger.exception("Glassdoor scraper failed -- returning %d partial results", len(listings))
    finally:
        await page.close()

    return listings


async def _parse_glassdoor_card(card: Any) -> Optional[JobListing]:
    """Parse a single Glassdoor job card."""

    # Title
    title_el = await card.query_selector(
        'a[data-test="job-title"], a.jobTitle, a.JobCard_jobTitle'
    )
    title = (await title_el.inner_text()).strip() if title_el else None
    if not title:
        return None

    # Company
    company_el = await card.query_selector(
        'span.EmployerProfile_compactEmployerName, div.d-flex a span, '
        'a[data-test="employer-short-name"]'
    )
    company = (await company_el.inner_text()).strip() if company_el else "Unknown"

    # Location
    location_el = await card.query_selector(
        'span.pr-xxsm, div.d-flex.loc, span[data-test="emp-location"]'
    )
    location = (await location_el.inner_text()).strip() if location_el else "Unknown"

    # URL
    link_el = await card.query_selector('a[data-test="job-title"], a.jobTitle')
    href = await link_el.get_attribute("href") if link_el else None
    if href and not href.startswith("http"):
        href = f"{GLASSDOOR_BASE}{href}"
    url = href or f"{GLASSDOOR_BASE}/job-listing/{uuid4().hex[:12]}"

    # Salary
    salary_el = await card.query_selector(
        'span[data-test="detailSalary"], div.salary-estimate'
    )
    salary_range = (await salary_el.inner_text()).strip() if salary_el else None

    # Remote
    is_remote = bool(location and "remote" in location.lower())

    # Easy apply
    easy_el = await card.query_selector('div.easyApply, span[class*="easyApply"]')
    is_easy_apply = easy_el is not None

    return JobListing(
        id=str(uuid4()),
        title=title,
        company=company,
        location=location,
        url=url,
        board=JobBoard.GLASSDOOR,
        ats_type=ATSType.UNKNOWN,
        salary_range=salary_range,
        description_snippet=None,
        posted_date=None,
        is_remote=is_remote,
        is_easy_apply=is_easy_apply,
    )
