"""ATS Detector -- identifies the Applicant Tracking System from a page.

Detects Workday, Greenhouse, Lever, iCIMS, Taleo, and other common ATS
platforms by inspecting URL patterns, page content, and DOM structure.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

from backend.shared.models.schemas import ATSType

logger = logging.getLogger(__name__)

_ATS_DOMAINS = {
    "linkedin.com": ATSType.LINKEDIN,
    "indeed.com": ATSType.INDEED,
    "myworkdayjobs.com": ATSType.WORKDAY,
    "myworkday.com": ATSType.WORKDAY,
    "workday.com": ATSType.WORKDAY,
    "greenhouse.io": ATSType.GREENHOUSE,
    "lever.co": ATSType.LEVER,
    "ashbyhq.com": ATSType.ASHBY,
    "icims.com": ATSType.ICIMS,
    "taleo.net": ATSType.TALEO,
    "taleo.com": ATSType.TALEO,
}


def detect_ats_from_url(url: str) -> ATSType:
    """Detect ATS type from URL only (no browser needed)."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return ATSType.UNKNOWN
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
        return ATSType.UNKNOWN
    for domain, ats_type in _ATS_DOMAINS.items():
        if host == domain or host.endswith(f".{domain}"):
            return ats_type
    return ATSType.UNKNOWN


async def detect_ats_type(page: Any) -> ATSType:
    """Detect the ATS type from the current page URL and content.

    Parameters
    ----------
    page:
        A Playwright Page on the application/job page.

    Returns
    -------
    ATSType
    """
    url = page.url

    # 1. Check URL patterns first (most reliable)
    ats_type = detect_ats_from_url(url)
    if ats_type is not ATSType.UNKNOWN:
        logger.info("ATS detected from URL: %s", ats_type.value)
        return ats_type

    # 2. Check page content / meta tags
    try:
        content_checks = await page.evaluate("""() => {
            const html = document.documentElement.outerHTML.toLowerCase();
            return {
                has_workday: html.includes('workday') || html.includes('wd-') || html.includes('wday'),
                has_greenhouse: html.includes('greenhouse') || html.includes('grnhse'),
                has_lever: html.includes('lever.co') || html.includes('lever-jobs'),
                has_ashby: html.includes('ashbyhq') || html.includes('ashby'),
                has_icims: html.includes('icims') || html.includes('pageobject'),
                has_taleo: html.includes('taleo') || html.includes('oracle.*careers'),
            };
        }""")

        if content_checks.get("has_workday"):
            return ATSType.WORKDAY
        if content_checks.get("has_greenhouse"):
            return ATSType.GREENHOUSE
        if content_checks.get("has_lever"):
            return ATSType.LEVER
        if content_checks.get("has_ashby"):
            return ATSType.ASHBY
        if content_checks.get("has_icims"):
            return ATSType.ICIMS
        if content_checks.get("has_taleo"):
            return ATSType.TALEO

    except Exception:
        logger.debug("ATS content detection failed", exc_info=True)

    logger.info("ATS type unknown for URL: %s", url)
    return ATSType.UNKNOWN
