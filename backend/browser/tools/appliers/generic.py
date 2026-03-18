# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Generic applier — best-effort form filling for unknown ATS platforms."""

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

_SUBMIT_BUTTON = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("Submit")',
    'button:has-text("Apply")',
    'button:has-text("Send")',
]


class GenericApplier(BaseApplier):
    """Best-effort applier for unknown ATS platforms."""

    PLATFORM = "unknown"

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
            # Check if there's a form on the page
            has_form = await self.page.query_selector("form")
            if not has_form:
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message="No application form found on page (unsupported ATS)",
                )

            await self._emit_step("Filling application form...")
            await self._fill_current_form(
                user_profile=user_profile,
                resume_text=resume_text,
                cover_letter=cover_letter,
                job_title=job.title,
                job_company=job.company,
                resume_file_path=resume_file_path,
            )

            await self._random_delay(0.5, 1.0)
            await self._emit_step("Submitting...")
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
            logger.error("Generic apply failed for %s: %s", job.title, exc, exc_info=True)
            return self._make_result(
                job_id, ApplicationStatus.FAILED,
                error_message=f"Apply error: {str(exc)[:200]}",
            )
