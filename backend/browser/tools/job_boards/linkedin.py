"""LinkedIn job board scraper using Playwright browser automation.

Uses LinkedIn's public jobs search (no authentication required) to discover
listings.  Note: LinkedIn is more aggressive with bot-detection, so this
scraper uses extra delays and careful navigation.  Returns partial results
on failure rather than raising.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.browser.anti_detect.stealth import apply_stealth
from backend.shared.models.schemas import ATSType, JobBoard, JobListing, SearchConfig

logger = logging.getLogger(__name__)

LINKEDIN_BASE = "https://www.linkedin.com"
LINKEDIN_JOBS = f"{LINKEDIN_BASE}/jobs/search"

MAX_PAGES = 2  # LinkedIn is stricter -- fewer pages

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
    """Return True if LinkedIn is showing a captcha, block, or auth wall."""
    # Standard captcha checks
    for sel in _BLOCK_SELECTORS:
        try:
            if await page.query_selector(sel):
                logger.warning("LinkedIn: block/captcha detected (selector: %s)", sel)
                return True
        except Exception:
            continue

    # LinkedIn auth wall detection
    auth_selectors = [
        "div.authwall-join-form",
        "section.join-form",
        "form.login__form",
    ]
    for sel in auth_selectors:
        try:
            if await page.query_selector(sel):
                logger.warning("LinkedIn: auth wall detected (selector: %s)", sel)
                return True
        except Exception:
            continue

    # URL-based auth wall check
    current_url = page.url or ""
    if "/authwall" in current_url or "/login" in current_url:
        logger.warning("LinkedIn: auth redirect detected in URL: %s", current_url)
        return True

    # Page title check
    try:
        title = (await page.title() or "").lower()
        if any(kw in title for kw in ("captcha", "blocked", "denied", "sign in", "just a moment")):
            logger.warning("LinkedIn: block detected via page title '%s'", title)
            return True
    except Exception:
        pass

    return False


async def scrape_linkedin(
    context: Any,  # BrowserContext
    search_config: SearchConfig,
    *,
    max_results: int = 12,
) -> List[JobListing]:
    """Scrape LinkedIn public job search for listings.

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
        query = " ".join(search_config.keywords[:5])
        location = search_config.locations[0] if search_config.locations else ""

        params: Dict[str, str] = {"keywords": query, "trk": "public_jobs_jobs-search-bar_search-submit"}
        if location:
            params["location"] = location
        if search_config.remote_only:
            params["f_WT"] = "2"  # LinkedIn remote filter

        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        search_url = f"{LINKEDIN_JOBS}?{param_str}"

        logger.info("LinkedIn scraper navigating to: %s", search_url)

        for page_num in range(MAX_PAGES):
            if len(listings) >= max_results:
                break

            url = search_url if page_num == 0 else f"{search_url}&start={page_num * 25}"

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Extra delay for LinkedIn anti-bot
            await page.wait_for_timeout(random.randint(2000, 4000))

            # Check for captcha / block / auth wall
            if await _is_blocked(page):
                logger.warning("LinkedIn: blocked on page %d -- returning %d partial results", page_num + 1, len(listings))
                break

            # Wait for job cards
            try:
                await page.wait_for_selector(
                    'div.base-card, div.job-search-card, ul.jobs-search__results-list li',
                    timeout=12000,
                )
            except Exception:
                logger.warning("LinkedIn: no job cards on page %d", page_num + 1)
                break

            cards = await page.query_selector_all(
                'div.base-card, div.job-search-card, li.jobs-search-results__list-item'
            )

            for card in cards:
                if len(listings) >= max_results:
                    break
                try:
                    listing = await _parse_linkedin_card(card)
                    if listing:
                        listings.append(listing)
                except Exception:
                    logger.debug("Failed to parse a LinkedIn card", exc_info=True)

            if page_num < MAX_PAGES - 1:
                await page.wait_for_timeout(random.randint(3000, 6000))

        logger.info("LinkedIn scraper found %d listings", len(listings))

    except Exception:
        logger.exception("LinkedIn scraper failed -- returning %d partial results", len(listings))
    finally:
        await page.close()

    return listings


async def _parse_linkedin_card(card: Any) -> Optional[JobListing]:
    """Parse a single LinkedIn job card."""

    # Title
    title_el = await card.query_selector(
        'h3.base-search-card__title, span.sr-only, a.base-card__full-link'
    )
    title = (await title_el.inner_text()).strip() if title_el else None
    if not title:
        return None

    # Company
    company_el = await card.query_selector(
        'h4.base-search-card__subtitle a, h4.base-search-card__subtitle'
    )
    company = (await company_el.inner_text()).strip() if company_el else "Unknown"

    # Location
    location_el = await card.query_selector(
        'span.job-search-card__location'
    )
    location = (await location_el.inner_text()).strip() if location_el else "Unknown"

    # URL
    link_el = await card.query_selector('a.base-card__full-link, a[href*="/jobs/view/"]')
    href = await link_el.get_attribute("href") if link_el else None
    url = href or f"{LINKEDIN_BASE}/jobs/view/{uuid4().hex[:12]}"

    # Date
    date_el = await card.query_selector('time, span.job-search-card__listdate')
    posted_date = None
    if date_el:
        posted_date = await date_el.get_attribute("datetime") or (await date_el.inner_text()).strip()

    # Remote
    is_remote = bool(location and "remote" in location.lower())

    # Easy Apply badge
    easy_el = await card.query_selector('span[class*="easy-apply"], span.result-benefits__text')
    is_easy_apply = easy_el is not None

    return JobListing(
        id=str(uuid4()),
        title=title,
        company=company,
        location=location,
        url=url,
        board=JobBoard.LINKEDIN,
        ats_type=ATSType.UNKNOWN,
        salary_range=None,  # LinkedIn rarely shows salary on cards
        description_snippet=None,
        posted_date=posted_date,
        is_remote=is_remote,
        is_easy_apply=is_easy_apply,
    )
