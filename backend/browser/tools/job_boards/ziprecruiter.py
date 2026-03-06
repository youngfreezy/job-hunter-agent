"""ZipRecruiter job board scraper using Playwright browser automation.

ZipRecruiter frequently shows auth/signup popups and email gates.
This scraper attempts to dismiss them automatically and returns partial
results on blocks rather than crashing the pipeline.
"""

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

# Auth / block / popup selectors
_BLOCK_SELECTORS = [
    "#captcha-form",
    "#px-captcha",
    ".cf-challenge-running",
    "#challenge-running",
    ".g-recaptcha",
    "#recaptcha",
    'div[class*="captcha"]',
]

_POPUP_CLOSE_SELECTORS = [
    'button[aria-label="Close"]',
    'button[aria-label="close"]',
    'button.modal-close',
    'button.close',
    'div[class*="modal"] button[class*="close"]',
    'div[class*="overlay"] button[class*="close"]',
    'button[data-testid="close"]',
    'div[class*="Modal"] button',
    # ZipRecruiter-specific signup/email gate dismiss
    'button[class*="dismiss"]',
    'a[class*="skip"]',
    'button:has-text("No thanks")',
    'button:has-text("Skip")',
    'button:has-text("Not now")',
]

_AUTH_SELECTORS = [
    'form[action*="login"]',
    'form[action*="signup"]',
    'div[class*="signup-modal"]',
    'div[class*="auth-modal"]',
    'div[class*="registration"]',
    'div[class*="SignUp"]',
    'div[class*="LoginModal"]',
]

# Signup/email gate modal (verified 2026-03) -- appears on first visit
_SIGNUP_MODAL_SELECTORS = [
    'div[role="dialog"] button[aria-label="Close"]',
    'div[aria-modal="true"] button[aria-label="Close"]',
    'div[role="dialog"] button[aria-label="close"]',
    'button[data-testid="modal-close"]',
    # Escape key as last resort
]

# Hardcoded card selectors (verified 2026-03) + DB fallback
_HARDCODED_CARD_SELECTORS = [
    'div[class*="job_result"], article[id^="job-card-"]',
    'article.job_result, div[class*="JobCard"]',
]


def _get_card_selectors(board: str) -> list[str]:
    """Return card selectors: DB-learned first, then hardcoded fallbacks."""
    try:
        from backend.shared.selector_memory import get_top_selectors
        db_sels = get_top_selectors(board, limit=3)
    except Exception:
        db_sels = []
    return db_sels + _HARDCODED_CARD_SELECTORS


def _build_query_variants(keywords: list[str]) -> list[str]:
    """Build per-keyword search queries.

    ZipRecruiter treats multi-keyword queries as AND, so search each
    keyword individually and combine results.
    """
    if not keywords:
        return ["software engineer"]
    return keywords[:5]


async def _dismiss_popups(page: Any) -> bool:
    """Try to dismiss any auth/signup popups. Returns True if one was found."""
    dismissed = False

    # First try the signup modal (most common blocker on ZipRecruiter)
    for sel in _SIGNUP_MODAL_SELECTORS:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(500)
                dismissed = True
                logger.info("ZipRecruiter: dismissed signup modal via %s", sel)
                return True
        except Exception:
            continue

    # Try Escape key to dismiss any modal
    try:
        dialog = await page.query_selector('div[role="dialog"], div[aria-modal="true"]')
        if dialog and await dialog.is_visible():
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
            # Check if it closed
            dialog_after = await page.query_selector('div[role="dialog"], div[aria-modal="true"]')
            if not dialog_after or not await dialog_after.is_visible():
                dismissed = True
                logger.info("ZipRecruiter: dismissed modal via Escape key")
                return True
    except Exception:
        pass

    # Generic close buttons
    for sel in _POPUP_CLOSE_SELECTORS:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(500)
                dismissed = True
                logger.info("ZipRecruiter: dismissed popup via %s", sel)
        except Exception:
            continue
    return dismissed


async def _is_blocked(page: Any) -> bool:
    """Return True if ZipRecruiter is showing a captcha, block, or auth wall."""
    for sel in _BLOCK_SELECTORS:
        try:
            if await page.query_selector(sel):
                logger.warning("ZipRecruiter: block/captcha detected (selector: %s)", sel)
                return True
        except Exception:
            continue

    # Check for auth wall that can't be dismissed
    for sel in _AUTH_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                # Try to dismiss it first
                if not await _dismiss_popups(page):
                    logger.warning("ZipRecruiter: auth wall detected (selector: %s)", sel)
                    return True
        except Exception:
            continue

    # Page title check
    try:
        title = (await page.title() or "").lower()
        if any(kw in title for kw in ("captcha", "blocked", "denied", "just a moment", "sign up", "sign in")):
            logger.warning("ZipRecruiter: block detected via page title '%s'", title)
            return True
    except Exception:
        pass

    return False


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
        location = search_config.locations[0] if search_config.locations else ""
        queries = _build_query_variants(search_config.keywords)

        base_params: Dict[str, str] = {}
        if search_config.remote_only:
            base_params["refine_by_location_type"] = "only_remote"
        elif location and location.lower() != "remote":
            base_params["location"] = location
            base_params["radius"] = "100"

        for query in queries:
            if len(listings) >= max_results:
                break

            params = {**base_params, "search": query}
            param_str = "&".join(f"{k}={v}" for k, v in params.items())
            search_url = f"{ZIPRECRUITER_JOBS}?{param_str}"

            logger.info("ZipRecruiter scraper navigating to: %s", search_url)

            for page_num in range(MAX_PAGES):
                if len(listings) >= max_results:
                    break

                url = search_url if page_num == 0 else f"{search_url}&page={page_num + 1}"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(random.randint(2000, 4000))

                # Dismiss any signup/auth popups
                await _dismiss_popups(page)

                # Check for captcha / block / auth wall
                if await _is_blocked(page):
                    logger.warning(
                        "ZipRecruiter: blocked on page %d -- returning %d partial results",
                        page_num + 1, len(listings),
                    )
                    break

                # Wait for job cards (try DB selectors too)
                card_selectors = _get_card_selectors("ziprecruiter")
                found_cards = False
                for sel in card_selectors:
                    try:
                        await page.wait_for_selector(sel, timeout=6000)
                        found_cards = True
                        break
                    except Exception:
                        continue

                if not found_cards:
                    logger.warning("ZipRecruiter: no job cards on page %d (query: %s)", page_num + 1, query)
                    break

                # Try all card selectors to find elements
                cards: list = []
                for sel in card_selectors:
                    cards = await page.query_selector_all(sel)
                    if cards:
                        break

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
        logger.exception("ZipRecruiter scraper failed -- returning %d partial results", len(listings))
    finally:
        await page.close()

    return listings


async def _parse_ziprecruiter_card(card: Any) -> Optional[JobListing]:
    """Parse a single ZipRecruiter job card.

    Selectors verified against live ZipRecruiter page (2026-03).
    Card structure: div.job_result_... > article#job-card-{id}
      - Title: button[aria-label] (main clickable title)
      - Company: a[data-testid="job-card-company"]
      - Location/Salary/Quick-apply: sequential <p> elements
    """

    # Title — the main title button has an aria-label like "View <title>"
    title_el = await card.query_selector('button[aria-label^="View "]')
    if title_el:
        title = (await title_el.inner_text()).strip()
    else:
        return None
    if not title:
        return None

    # Company
    company_el = await card.query_selector('a[data-testid="job-card-company"]')
    company = (await company_el.inner_text()).strip() if company_el else "Unknown"

    # Location and Salary come from sequential <p> elements after the title.
    # p[0] = company, p[1] = location, p[2] = salary (optional), p[3] = "Quick apply" (optional)
    p_elements = await card.query_selector_all("p")
    location = "Unknown"
    salary_range = None
    is_easy_apply = False

    for p_el in p_elements:
        text = (await p_el.inner_text()).strip()
        if not text:
            continue
        # Location pattern: "City, ST" or "City, ST · Remote"
        if "," in text and any(c.isupper() for c in text) and text != company:
            location = text
        # Salary pattern: starts with $ or contains /yr, /hr
        elif text.startswith("$") or "/yr" in text or "/hr" in text:
            salary_range = text
        # Quick apply badge
        elif text.lower() in ("quick apply", "1-click apply"):
            is_easy_apply = True

    # URL — extract actual href from the job title link or any link in the card
    url = None
    # Try the title button's parent link or a direct <a> with the job URL
    link_el = await card.query_selector('a[href*="/jobs/"], a[href*="/job/"]')
    if link_el:
        url = await link_el.get_attribute("href") or None
    # Fallback: try the title button which may have a data-href or onclick target
    if not url and title_el:
        url = await title_el.get_attribute("data-href") or None
    # Last resort: construct from article ID (may 404)
    if not url:
        article_el = await card.query_selector("article[id^='job-card-']")
        if article_el:
            article_id = await article_el.get_attribute("id") or ""
            job_key = article_id.replace("job-card-", "")
            url = f"{ZIPRECRUITER_BASE}/jobs/{job_key}"
    if not url:
        url = f"{ZIPRECRUITER_BASE}/jobs/{uuid4().hex[:12]}"

    is_remote = bool(location and "remote" in location.lower())

    return JobListing(
        id=str(uuid4()),
        title=title,
        company=company,
        location=location,
        url=url,
        board=JobBoard.ZIPRECRUITER,
        ats_type=ATSType.UNKNOWN,
        salary_range=salary_range,
        description_snippet=None,
        posted_date=None,
        is_remote=is_remote,
        is_easy_apply=is_easy_apply,
    )
