# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Generic Applier -- fallback for unknown ATS platforms.

Tries to find any Apply button, fill the form via form_filler, and submit.
Returns SKIPPED if it can't figure out the form (triggers browser-use fallback).
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from backend.shared.models.schemas import ApplicationResult, ApplicationStatus, JobListing

from .base import BaseApplier

logger = logging.getLogger(__name__)

_APPLY_SELECTORS = [
    'button:has-text("Apply")',
    'a:has-text("Apply")',
    'button:has-text("Apply now")',
    'a:has-text("Apply now")',
    'button:has-text("Apply for this job")',
    'a:has-text("Apply for this job")',
    'button[data-testid="apply-button"]',
]

_SUBMIT_SELECTORS = [
    'button[type="submit"]',
    'button:has-text("Submit")',
    'button:has-text("Submit Application")',
    'button:has-text("Submit application")',
    'input[type="submit"]',
]

_NEXT_SELECTORS = [
    'button:has-text("Next")',
    'button:has-text("Continue")',
    'button:has-text("Save and continue")',
]

MAX_STEPS = 8


class GenericApplier(BaseApplier):
    PLATFORM = "generic"

    async def apply(
        self,
        job: JobListing,
        user_profile: Dict[str, str],
        resume_text: str,
        cover_letter: str,
        resume_file_path: Optional[str] = None,
    ) -> ApplicationResult:
        await self._emit_step("Looking for Apply button...")

        # Try to find and click an Apply button
        clicked = await self._click_selector(_APPLY_SELECTORS, "apply_button", timeout=5000)
        if not clicked:
            # Maybe the form is already visible on the page
            from backend.browser.tools.form_filler import extract_form_fields
            fields = await extract_form_fields(self.page)
            if not fields:
                logger.info("Generic applier: no apply button or form found, skipping")
                return self._make_result(job.id, ApplicationStatus.SKIPPED,
                                         error_message="No apply button or form found")

        await self._random_delay(1.0, 2.0)
        await self._wait_for_navigation()

        # Multi-step form loop
        for step in range(MAX_STEPS):
            # Fill whatever form is on the current page
            result = await self._fill_current_form(
                user_profile=user_profile,
                resume_text=resume_text,
                cover_letter=cover_letter,
                job_title=job.title,
                job_company=job.company,
                resume_file_path=resume_file_path,
            )

            # Try to upload resume if there's a file input
            if resume_file_path:
                await self._upload_resume(resume_file_path)

            await self._random_delay(0.5, 1.0)

            # Try Submit first
            submitted = await self._click_selector(_SUBMIT_SELECTORS, "submit_button", timeout=3000)
            if submitted:
                await self._random_delay(1.0, 2.0)
                await self._wait_for_navigation()
                # Post-submit checks (verification, captcha, confirmation, failure)
                result = await self._post_submit_check(job.id, cover_letter)
                if result.status == ApplicationStatus.SUBMITTED:
                    return result
                # Might have been a Next disguised as Submit, continue
                continue

            # Try Next button
            has_next = await self._click_selector(_NEXT_SELECTORS, "next_button", timeout=3000)
            if has_next:
                await self._random_delay(0.5, 1.0)
                await self._wait_for_navigation()
                continue

            # No Submit or Next found -- check if we're on a confirmation page
            if await self._detect_confirmation():
                await self._emit_step("Application submitted!")
                return self._make_result(job.id, ApplicationStatus.SUBMITTED,
                                         cover_letter_used=cover_letter)

            # Nothing worked -- break out
            break

        # Post-loop: run full post-submit checks (verification, captcha, confirmation, failure)
        result = await self._post_submit_check(job.id, cover_letter)
        if result.status != ApplicationStatus.FAILED:
            return result

        # Generic couldn't complete -- return SKIPPED for browser-use fallback
        logger.info("Generic applier could not complete application, returning SKIPPED")
        return self._make_result(job.id, ApplicationStatus.SKIPPED,
                                 error_message="Generic applier could not determine submission flow")
