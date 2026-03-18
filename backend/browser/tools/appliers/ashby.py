# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Ashby ATS applier — single-page application form."""

from __future__ import annotations

import logging
from typing import Dict, Optional

from backend.browser.tools.appliers.base import BaseApplier
from backend.shared.models.schemas import (
    ApplicationResult,
    ApplicationStatus,
    JobListing,
)

logger = logging.getLogger(__name__)

_APPLY_BUTTON = [
    'button:has-text("Apply")',
    'a:has-text("Apply")',
    'button[data-testid="apply-button"]',
]

_SUBMIT_BUTTON = [
    'button:has-text("Submit application")',
    'button:has-text("Submit")',
    'button[type="submit"]',
]


class AshbyApplier(BaseApplier):
    """Apply to jobs on jobs.ashbyhq.com via Playwright form filling."""

    PLATFORM = "ashby"

    async def apply(
        self,
        job: JobListing,
        user_profile: Dict[str, str],
        resume_text: str,
        cover_letter: str,
        resume_file_path: Optional[str] = None,
    ) -> ApplicationResult:
        job_id = str(job.id)

        try:
            # Ashby forms are often inline on the posting page
            await self._emit_step("Looking for application form...")
            has_form = await self.page.query_selector('form, [data-testid="application-form"]')
            if not has_form:
                clicked = await self._click_selector(_APPLY_BUTTON, "apply_button", timeout=5000)
                if not clicked:
                    has_form = await self.page.query_selector("form")
                    if not has_form:
                        return self._make_result(
                            job_id, ApplicationStatus.FAILED,
                            error_message="Could not find application form",
                        )
                await self._random_delay(1.0, 2.0)
                await self._wait_for_navigation()

            # Fill the form
            await self._fill_current_form(
                user_profile=user_profile,
                resume_text=resume_text,
                cover_letter=cover_letter,
                job_title=job.title,
                job_company=job.company,
                resume_file_path=resume_file_path,
            )

            # Submit
            await self._random_delay(0.5, 1.0)
            await self._emit_step("Submitting application...")
            submit_clicked = await self._click_selector(_SUBMIT_BUTTON, "submit_button", timeout=5000)
            if not submit_clicked:
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message="Could not find Submit button",
                )

            await self._random_delay(2.0, 4.0)
            await self._wait_for_navigation()

            await self._capture_screenshot(job)
            return await self._post_submit_check(job_id, cover_letter)

        except Exception as exc:
            logger.error("Ashby apply failed for %s: %s", job.title, exc, exc_info=True)
            return self._make_result(
                job_id, ApplicationStatus.FAILED,
                error_message=f"Ashby apply error: {str(exc)[:200]}",
            )
