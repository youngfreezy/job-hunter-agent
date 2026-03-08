# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Indeed Apply applier.

Handles Indeed's native apply flow: click Apply, fill multi-page forms,
and submit. If the job redirects to an external ATS site, returns SKIPPED
so a different applier can handle it.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional
from urllib.parse import urlparse

from backend.shared.models.schemas import ApplicationStatus, JobListing

from .base import BaseApplier

logger = logging.getLogger(__name__)

# -- Selector groups --------------------------------------------------------

APPLY_BUTTON = [
    "#indeedApplyButton",
    "button.jobsearch-IndeedApplyButton",
    'button:has-text("Apply now")',
    'button:has-text("Apply on Indeed")',
]

NEXT_BUTTON = [
    'button:has-text("Continue")',
    'button[data-testid="continue-button"]',
]

SUBMIT_BUTTON = [
    'button:has-text("Submit your application")',
    'button:has-text("Submit application")',
    'button:has-text("Submit")',
    'button[data-testid="submit-button"]',
    'button.ia-continueButton[type="submit"]',
]

MAX_PAGES = 6


class IndeedApplier(BaseApplier):
    """Applies to jobs via Indeed's native application flow."""

    PLATFORM = "indeed"

    async def apply(
        self,
        job: JobListing,
        user_profile: Dict[str, str],
        resume_text: str,
        cover_letter: str,
        resume_file_path: Optional[str] = None,
    ):
        job_id = str(job.id)

        try:
            # 1. Click Apply button
            await self._emit_step("Clicking Apply button")
            clicked = await self._click_selector(APPLY_BUTTON, "apply_button")
            if not clicked:
                return self._make_result(
                    job_id, ApplicationStatus.SKIPPED,
                    error_message="Apply button not found — likely requires auth",
                )

            await self._random_delay(1.5, 2.5)
            await self._wait_for_navigation()

            # 2. Check for external redirect
            if self._is_external_redirect():
                await self._emit_step("Job redirects to external site -- skipping")
                return self._make_result(
                    job_id, ApplicationStatus.SKIPPED,
                    error_message="External ATS redirect detected",
                )

            # 3. Multi-page form loop
            for page_num in range(1, MAX_PAGES + 1):
                await self._emit_step(f"Processing form page {page_num}")
                await self._random_delay(0.5, 1.0)

                # Fill form fields on current page
                await self._fill_current_form(
                    user_profile=user_profile,
                    resume_text=resume_text,
                    cover_letter=cover_letter,
                    job_title=job.title,
                    job_company=job.company,
                    resume_file_path=resume_file_path,
                )

                # Upload resume if file input present
                if resume_file_path:
                    await self._upload_resume(resume_file_path)

                await self._random_delay(0.5, 1.0)

                # Try Submit (final page)
                if await self._click_selector(SUBMIT_BUTTON, "submit_button", timeout=2000):
                    await self._emit_step("Clicked Submit application")
                    await self._wait_for_navigation()
                    break

                # Try Continue (intermediate page)
                if await self._click_selector(NEXT_BUTTON, "next_button", timeout=2000):
                    await self._emit_step("Clicked Continue")
                    await self._wait_for_navigation()
                    await self._random_delay(0.5, 1.0)
                    continue

                # No navigation button found
                logger.warning("No Continue/Submit button found at page %d", page_num)
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message=f"Stuck at page {page_num} -- no navigation button found",
                )
            else:
                # Exhausted MAX_PAGES without submitting
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message=f"Exceeded {MAX_PAGES} pages without submitting",
                )

            # 4. Post-submit checks (verification, captcha, confirmation, failure)
            await self._random_delay(1.0, 2.0)
            return await self._post_submit_check(job_id, cover_letter)

        except Exception as exc:
            logger.exception("Indeed apply failed for job %s", job_id)
            return self._make_result(
                job_id, ApplicationStatus.FAILED,
                error_message=str(exc),
            )

    # ------------------------------------------------------------------
    # Indeed-specific helpers
    # ------------------------------------------------------------------

    def _is_external_redirect(self) -> bool:
        """Check whether the current URL has left Indeed's domain."""
        try:
            current = urlparse(self.page.url)
            return "indeed" not in (current.hostname or "")
        except Exception:
            return False
