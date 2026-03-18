# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Playwright applier dispatcher — routes to ATS-specific applier based on URL.

Drop-in replacement for apply_with_skyvern(). Uses the existing BaseApplier
infrastructure (form_filler, apply_selectors, confirmation detection) with
thin ATS-specific subclasses for navigation flow.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.browser.tools.appliers.ashby import AshbyApplier
from backend.browser.tools.appliers.generic import GenericApplier
from backend.browser.tools.appliers.greenhouse import GreenhouseApplier
from backend.browser.tools.appliers.lever import LeverApplier
from backend.browser.tools.ats_detector import detect_ats_from_url
from backend.shared.models.schemas import (
    ApplicationResult,
    ApplicationStatus,
    ATSType,
    JobListing,
)

logger = logging.getLogger(__name__)

_APPLIER_MAP = {
    ATSType.GREENHOUSE: GreenhouseApplier,
    ATSType.LEVER: LeverApplier,
    ATSType.ASHBY: AshbyApplier,
}


async def apply_with_playwright(
    job: JobListing,
    user_profile: Dict[str, str],
    resume_text: str,
    cover_letter: str,
    resume_file_path: Optional[str],
    session_id: str,
    page: Any,
) -> ApplicationResult:
    """Apply to a job using Playwright browser automation + Claude Haiku.

    Drop-in replacement for apply_with_skyvern(). Routes to the correct
    ATS-specific applier based on the job URL, falling back to GenericApplier.
    """
    # Detect ATS from current page URL (may have redirected from original)
    url = page.url if hasattr(page, "url") else job.url
    ats_type = detect_ats_from_url(url)
    if ats_type == ATSType.UNKNOWN and job.ats_type:
        ats_type = job.ats_type if isinstance(job.ats_type, ATSType) else ATSType(job.ats_type)

    applier_cls = _APPLIER_MAP.get(ats_type, GenericApplier)
    logger.info(
        "Playwright apply: %s @ %s — using %s (ats=%s)",
        job.title, job.company, applier_cls.__name__, ats_type,
    )

    applier = applier_cls(page, session_id)
    return await applier.run(
        job=job,
        user_profile=user_profile,
        resume_text=resume_text,
        cover_letter=cover_letter,
        resume_file_path=resume_file_path,
    )
