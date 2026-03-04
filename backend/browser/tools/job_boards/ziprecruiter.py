"""ZipRecruiter job board scraper using Playwright browser automation."""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.browser.anti_detect.stealth import apply_stealth
from backend.shared.models.schemas import ATSType, JobBoard, JobListing, SearchConfig

logger = logging.getLogger(__name__)

ZIPRECRUITER_BASE = "https://www.ziprecruiter.com"
ZIPRECRUITER_JOBS = f"{ZIPRECRUITER_BASE}/jobs-search"

MAX_PAGES = 2


async def scrape_ziprecruiter(
    context: Any,
    search_config: SearchConfig,
    *,
    max_results: int = 10,
) -> List[JobListing]:
    """Scrape ZipRecruiter for job listings matching *search_config*.

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
    """
    page = await context.new_page()
    await apply_stealth(page)
    listings: List[JobListing] = []

    try:
        query = " ".join(search_config.keywords)
        location = search_config.locations[0] if search_config.locations else ""

        params: Dict[str, str] = {"search": query}
        if location and location.lower() != "remote":
            params["location"] = location
        if search_config.remote_only:
            params["refine_by_location_type"] = "only_remote"

        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        search_url = f"{ZIPRECRUITER_JOBS}?{param_str}"

        logger.info("ZipRecruiter scraper navigating to: %s", search_url)

        for page_num in range(MAX_PAGES):
            if len(listings) >= max_results:
                break

            url = search_url if page_num == 0 else f"{search_url}&page={page_num + 1}"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.randint(2000, 4000))

            try:
                await page.wait_for_selector(
                    'article.job_result, div.job_content, div[class*="JobCard"]',
                    timeout=10000,
                )
            except Exception:
                logger.warning("ZipRecruiter: no job cards on page %d", page_num + 1)
                break

            cards = await page.query_selector_all(
                'article.job_result, div.job_content, div[class*="JobCard"]'
            )

            for card in cards:
                if len(listings) >= max_results:
                    break
                try:
                    listing = await _parse_ziprecruiter_card(card)
                    if listing:
                        listings.append(listing)
                except Exception:
                    logger.debug("Failed to parse a ZipRecruiter card", exc_info=True)

            if page_num < MAX_PAGES - 1:
                await page.wait_for_timeout(random.randint(2000, 5000))

        logger.info("ZipRecruiter scraper found %d listings", len(listings))

    except Exception:
        logger.exception("ZipRecruiter scraper failed")
        raise
    finally:
        await page.close()

    return listings


async def _parse_ziprecruiter_card(card: Any) -> Optional[JobListing]:
    """Parse a single ZipRecruiter job card."""

    # Title
    title_el = await card.query_selector(
        'h2.job_title a, a[data-testid="job-title"], h2[class*="title"] a'
    )
    title = (await title_el.inner_text()).strip() if title_el else None
    if not title:
        return None

    # Company
    company_el = await card.query_selector(
        'a.t_org_link, p.company_name, span[class*="company"]'
    )
    company = (await company_el.inner_text()).strip() if company_el else "Unknown"

    # Location
    location_el = await card.query_selector(
        'span.location, p.job_location, span[class*="location"]'
    )
    location = (await location_el.inner_text()).strip() if location_el else "Unknown"

    # URL
    link_el = await card.query_selector('h2.job_title a, a[data-testid="job-title"]')
    href = await link_el.get_attribute("href") if link_el else None
    if href and not href.startswith("http"):
        href = f"{ZIPRECRUITER_BASE}{href}"
    url = href or f"{ZIPRECRUITER_BASE}/jobs/{uuid4().hex[:12]}"

    # Salary
    salary_el = await card.query_selector(
        'span.salary, span[class*="salary"], div[data-testid="salary"]'
    )
    salary_range = (await salary_el.inner_text()).strip() if salary_el else None

    # Snippet
    snippet_el = await card.query_selector(
        'p.job_snippet, div[class*="snippet"]'
    )
    snippet = (await snippet_el.inner_text()).strip() if snippet_el else None

    # Date
    date_el = await card.query_selector('span.just_posted, time, span[class*="date"]')
    posted_date = (await date_el.inner_text()).strip() if date_el else None

    is_remote = bool(location and "remote" in location.lower())

    # 1-click apply badge
    easy_el = await card.query_selector(
        'span[class*="one_click"], button[class*="quick_apply"]'
    )
    is_easy_apply = easy_el is not None

    return JobListing(
        id=str(uuid4()),
        title=title,
        company=company,
        location=location,
        url=url,
        board=JobBoard.ZIPRECRUITER,
        ats_type=ATSType.UNKNOWN,
        salary_range=salary_range,
        description_snippet=snippet,
        posted_date=posted_date,
        is_remote=is_remote,
        is_easy_apply=is_easy_apply,
    )
