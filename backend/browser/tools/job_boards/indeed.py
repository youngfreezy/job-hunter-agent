"""Indeed job board scraper using Playwright browser automation.

Navigates to Indeed's search page, enters query parameters, and extracts
job listings from the results pages.  Returns partial results on failure
rather than raising, so the pipeline can continue with other boards.
"""

from __future__ import annotations

import logging
import random
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4
from urllib.parse import urlencode

from backend.browser.anti_detect.stealth import apply_stealth
from backend.shared.config import settings
from backend.shared.models.schemas import ATSType, JobBoard, JobListing, SearchConfig

logger = logging.getLogger(__name__)

INDEED_BASE = "https://www.indeed.com"
INDEED_SEARCH = f"{INDEED_BASE}/jobs"

# Continue beyond previously seen results, with a bounded cloud-session cost.
MAX_PAGES = 3

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
    """Inspect the current DOM once, avoiding many cloud protocol round trips."""
    return await page.evaluate("""selectors => {
        const visible = el => !!el && el.getClientRects().length > 0
            && getComputedStyle(el).visibility !== 'hidden';
        return selectors.some(s => Array.from(document.querySelectorAll(s)).some(visible))
            || /captcha|blocked|denied|robot|just a moment/i.test(document.title);
    }""", _BLOCK_SELECTORS)


async def _read_cards(page: Any) -> list[dict]:
    """Read one serializable snapshot rather than remote handles for every field."""
    return await page.evaluate("""() => {
        let cards = Array.from(document.querySelectorAll('div.job_seen_beacon'));
        if (!cards.length) cards = Array.from(document.querySelectorAll('td.resultContent'));
        if (!cards.length) cards = Array.from(document.querySelectorAll('div[class*="cardOutline"]'));
        return cards.map(card => {
            const text = selector => card.querySelector(selector)?.innerText?.trim() || null;
            const link = card.querySelector('h2.jobTitle a, a[data-jk]');
            return {
                title: text('h2.jobTitle a span[title], h2.jobTitle span, a[data-jk] span'),
                company: text('span[data-testid="company-name"], span.companyName, span.company'),
                location: text('div[data-testid="text-location"], div.companyLocation'),
                href: link?.getAttribute('href'), job_key: link?.getAttribute('data-jk'),
                salary_range: text('div[class*="salary-snippet"], div.metadata.salary-snippet-container span'),
                description_snippet: text('div.job-snippet, div[class*="job-snippet"], td.snip') || card.innerText.trim(),
                posted_date: text('span.date, span[class*="date"]'),
                is_easy_apply: !!card.querySelector('span[class*="easily-apply"], span.iaLabel') || /easily apply/i.test(card.innerText)
            };
        });
    }""")


def matches_search(listing: JobListing, search: SearchConfig) -> bool:
    if any(term.lower() in listing.title.lower() for term in search.exclude_title_keywords):
        return False
    if listing.company.lower() in {c.lower() for c in search.exclude_companies}:
        return False
    text = f"{listing.location} {listing.description_snippet or ''}".lower()
    return not search.work_arrangements or any(a in text for a in search.work_arrangements)


async def scrape_indeed(
    context: Any,  # BrowserContext
    search_config: SearchConfig,
    *,
    max_results: int = 15,
    excluded_urls: Optional[set[str]] = None,
    excluded_companies: Optional[set[str]] = None,
    excluded_job_keys: Optional[set[str]] = None,
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
    # Browserbase Live View initially targets its existing tab. Reuse it so
    # the embedded browser shows the actual discovery work.
    pages = context.pages
    page = pages[0] if pages else await context.new_page()
    if settings.BROWSER_MODE != "browserbase":
        await apply_stealth(page)
    listings: List[JobListing] = []
    seen = set(excluded_urls or ())
    seen_job_keys = set(excluded_job_keys or ())
    blocked_companies = {company.lower().strip() for company in (excluded_companies or ())}

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
            param_str = urlencode(params)
            search_url = f"{INDEED_SEARCH}?{param_str}"

            logger.info("Indeed scraper navigating to: %s", search_url)

            for page_num in range(MAX_PAGES):
                if len(listings) >= max_results:
                    break

                url = search_url if page_num == 0 else f"{search_url}&start={page_num * 10}"
                await page.goto(url, wait_until="domcontentloaded", timeout=90000)
                logger.info("Indeed results page %d loaded (query: %s)", page_num + 1, query)
                # Browserbase's managed solver runs in the cloud browser.
                await page.wait_for_timeout(random.randint(3000, 6000))

                # Allow supported challenges time to complete automatically.
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
                    if not listings:
                        raise RuntimeError("Browserbase could not resolve Indeed's access challenge within the wait period. The cloud session did not reach job results.")
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

                cards = await _read_cards(page)
                logger.info("Indeed reading %d cards on page %d", len(cards), page_num + 1)

                for card in cards:
                    if len(listings) >= max_results:
                        break
                    try:
                        listing = _parse_indeed_card(card)
                        if not listing or listing.url in seen:
                            continue
                        seen.add(listing.url)
                        company = listing.company.lower().strip()
                        job_key = f"{listing.title.lower().strip()}|{company}"
                        if company in blocked_companies or job_key in seen_job_keys:
                            continue
                        if matches_search(listing, search_config):
                            seen_job_keys.add(job_key)
                            listings.append(listing)
                    except Exception:
                        logger.debug("Failed to parse an Indeed card", exc_info=True)
                logger.info("Indeed has %d eligible listings after page %d", len(listings), page_num + 1)

                if page_num < MAX_PAGES - 1:
                    await page.wait_for_timeout(random.randint(2000, 5000))

        logger.info("Indeed scraper found %d listings", len(listings))

    except Exception:
        logger.exception("Indeed scraper failed -- returning %d partial results", len(listings))
        if not listings:
            raise
    finally:
        await page.close()

    return listings


def _parse_indeed_card(card: dict) -> Optional[JobListing]:
    """Validate a job card snapshot and normalize its Indeed URL."""
    title = card.get("title")
    if not title:
        return None
    href = card.get("href")
    job_key = card.get("job_key")
    if job_key and re.fullmatch(r"[a-zA-Z0-9]+", job_key):
        href = f"{INDEED_BASE}/viewjob?jk={job_key}"
    if href and not href.startswith("http"):
        href = f"{INDEED_BASE}{href}"
    from backend.browser.indeed_policy import is_indeed_url
    if not href or not is_indeed_url(href):
        return None
    location = card.get("location") or "Unknown"
    return JobListing(
        id=str(uuid4()), title=title, company=card.get("company") or "Unknown",
        location=location, url=href, board=JobBoard.INDEED, ats_type=ATSType.INDEED,
        salary_range=card.get("salary_range"),
        description_snippet=card.get("description_snippet"),
        posted_date=card.get("posted_date"), is_remote="remote" in location.lower(),
        is_easy_apply=bool(card.get("is_easy_apply")),
    )
