# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""ATS Detector -- identifies the Applicant Tracking System from a page.

Detects Workday, Greenhouse, Lever, iCIMS, Taleo, and other common ATS
platforms by inspecting URL patterns, page content, and DOM structure.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from backend.shared.models.schemas import ATSType

logger = logging.getLogger(__name__)

# URL-pattern -> ATS type mapping
_URL_PATTERNS = [
    (re.compile(r"linkedin\.com/jobs", re.I), ATSType.LINKEDIN),
    (re.compile(r"myworkday(jobs)?\.com|workday\.com", re.I), ATSType.WORKDAY),
    (re.compile(r"greenhouse\.io|boards\.greenhouse", re.I), ATSType.GREENHOUSE),
    (re.compile(r"lever\.co|jobs\.lever", re.I), ATSType.LEVER),
    (re.compile(r"ashbyhq\.com|jobs\.ashbyhq", re.I), ATSType.ASHBY),
    (re.compile(r"icims\.com|careers-.*\.icims", re.I), ATSType.ICIMS),
    (re.compile(r"taleo\.(net|com)|oracle.*cloud.*taleo", re.I), ATSType.TALEO),
]


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
    for pattern, ats_type in _URL_PATTERNS:
        if pattern.search(url):
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
