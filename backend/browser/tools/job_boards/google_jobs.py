# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Google Jobs scraper using Playwright browser automation.

Google Jobs results appear inline in Google search with the "jobs" chip.
This scraper navigates to a Google search with job-intent and extracts
the embedded job listings.  Returns partial results on failure rather
than raising.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus
from uuid import uuid4

from backend.browser.anti_detect.stealth import apply_stealth
from backend.shared.models.schemas import ATSType, JobBoard, JobListing, SearchConfig

logger = logging.getLogger(__name__)

GOOGLE_BASE = "https://www.google.com"

MAX_SCROLL = 3  # Number of times to scroll within the jobs panel

# Captcha / block selectors for Google
_BLOCK_SELECTORS = [
    "#captcha-form",
    "#recaptcha",
    ".g-recaptcha",
    'div[id="captcha"]',
    'form[action*="sorry"]',       # Google's "unusual traffic" page
    'div[id="infoDiv"]',           # Google's block info page
]


async def _is_blocked(page: Any) -> bool:
    """Return True if Google is showing a captcha or block page."""
    for sel in _BLOCK_SELECTORS:
        try:
            if await page.query_selector(sel):
                logger.warning("Google Jobs: block/captcha detected (selector: %s)", sel)
                return True
        except Exception:
            continue
    try:
        title = (await page.title() or "").lower()
        current_url = page.url or ""
        if "sorry" in current_url or "/sorry/" in current_url:
            logger.warning("Google Jobs: unusual traffic page detected")
            return True
        if any(kw in title for kw in ("captcha", "blocked", "unusual traffic")):
            logger.warning("Google Jobs: block detected via page title '%s'", title)
            return True
    except Exception:
        pass
    return False


async def scrape_google_jobs(
    context: Any,
    search_config: SearchConfig,
    *,
    max_results: int = 12,
) -> List[JobListing]:
    """Scrape Google Jobs for listings matching *search_config*.

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
        query_parts = search_config.keywords[:5] + ["jobs"]
        if search_config.locations and search_config.locations[0].lower() != "remote":
            query_parts.append(search_config.locations[0])
        if search_config.remote_only:
            query_parts.append("remote")

        query = " ".join(query_parts)
        search_url = f"{GOOGLE_BASE}/search?q={quote_plus(query)}&ibp=htl;jobs"

        logger.info("Google Jobs scraper navigating to: %s", search_url)

        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(random.randint(2000, 4000))

        # Check for captcha / block
        if await _is_blocked(page):
            logger.warning("Google Jobs: blocked -- returning empty results")
            return listings

        # Wait for the jobs panel to load
        try:
            await page.wait_for_selector(
                'div.gws-plugins-horizon-jobs__li-ed, li.iFjolb',
                timeout=12000,
            )
        except Exception:
            logger.warning("Google Jobs: job panel did not load")
            return listings

        # Scroll the jobs panel to load more results
        jobs_container = await page.query_selector(
            'div#search, div.gws-plugins-horizon-jobs__tl-lvc, div[role="list"]'
        )

        for scroll_round in range(MAX_SCROLL):
            if len(listings) >= max_results:
                break

            cards = await page.query_selector_all(
                'div.gws-plugins-horizon-jobs__li-ed, li.iFjolb, div[data-ved] div.pE8vnd'
            )

            for card in cards:
                if len(listings) >= max_results:
                    break
                try:
                    listing = await _parse_google_card(card)
                    if listing:
                        # Dedup by title+company
                        key = f"{listing.title}|{listing.company}"
                        existing = {f"{l.title}|{l.company}" for l in listings}
                        if key not in existing:
                            listings.append(listing)
                except Exception:
                    logger.debug("Failed to parse a Google Jobs card", exc_info=True)

            # Scroll the jobs panel
            if jobs_container:
                await jobs_container.evaluate("el => el.scrollTop += 600")
                await page.wait_for_timeout(random.randint(1500, 3000))

        logger.info("Google Jobs scraper found %d listings", len(listings))

    except Exception:
        logger.exception("Google Jobs scraper failed -- returning %d partial results", len(listings))
    finally:
        await page.close()

    return listings


async def _parse_google_card(card: Any) -> Optional[JobListing]:
    """Parse a single Google Jobs card."""

    # Title
    title_el = await card.query_selector(
        'div.BjJfJf, h2.KLsYvd, div[role="heading"]'
    )
    title = (await title_el.inner_text()).strip() if title_el else None
    if not title:
        return None

    # Company
    company_el = await card.query_selector(
        'div.vNEEBe, div.nJlIMc, span.nJlIMc'
    )
    company = (await company_el.inner_text()).strip() if company_el else "Unknown"

    # Location
    location_el = await card.query_selector(
        'div.Qk80Jf, span.Qk80Jf, div[class*="location"]'
    )
    location = (await location_el.inner_text()).strip() if location_el else "Unknown"

    # Salary
    salary_el = await card.query_selector(
        'span.LL4CDc, div[class*="salary"]'
    )
    salary_range = (await salary_el.inner_text()).strip() if salary_el else None

    # Date
    date_el = await card.query_selector('span.LL4CDc:last-of-type, span[class*="posted"]')
    posted_date = (await date_el.inner_text()).strip() if date_el else None

    # Google Jobs doesn't give direct apply URLs on the card -- use a search link
    url = f"https://www.google.com/search?q={quote_plus(title + ' ' + company + ' job apply')}"

    is_remote = bool(location and "remote" in location.lower())

    return JobListing(
        id=str(uuid4()),
        title=title,
        company=company,
        location=location,
        url=url,
        board=JobBoard.GOOGLE_JOBS,
        ats_type=ATSType.UNKNOWN,
        salary_range=salary_range,
        description_snippet=None,
        posted_date=posted_date,
        is_remote=is_remote,
        is_easy_apply=False,
    )
