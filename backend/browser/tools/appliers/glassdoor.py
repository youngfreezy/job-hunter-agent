# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Glassdoor apply flow.

Handles both the Easy Apply modal and external redirects. If the job
redirects to a known ATS (Greenhouse, Lever, etc.), returns SKIPPED so the
registry can re-dispatch to the appropriate ATS applier.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Optional

from backend.shared.models.schemas import ApplicationStatus, JobListing

from .base import BaseApplier

logger = logging.getLogger(__name__)

# -- Selector groups --------------------------------------------------------

APPLY_BUTTON = [
    'button:has-text("Easy Apply")',
    'button:has-text("Apply")',
    'button[data-test="applyButton"]',
]

NEXT_BUTTON = [
    'button:has-text("Continue")',
    'button:has-text("Next")',
]

SUBMIT_BUTTON = [
    'button:has-text("Submit")',
    'button[type="submit"]',
]

CAPTCHA_SELECTOR = "#px-captcha"

# ATS domains that indicate the job redirected away from Glassdoor
_ATS_REDIRECT_PATTERNS = re.compile(
    r"(greenhouse\.io|lever\.co|myworkdayjobs\.com|icims\.com|smartrecruiters\.com"
    r"|jobvite\.com|taleo\.net|ultipro\.com|breezy\.hr|ashbyhq\.com)",
    re.IGNORECASE,
)

MAX_STEPS = 6


class GlassdoorApplier(BaseApplier):
    """Applies to jobs via Glassdoor Easy Apply or detects external redirects."""

    PLATFORM = "glassdoor"

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
            # 1. Check for PerimeterX captcha
            if await self._has_captcha():
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message="PerimeterX captcha detected -- cannot proceed",
                )

            # 2. Click Apply button
            await self._emit_step("Clicking Apply button")
            clicked = await self._click_selector(APPLY_BUTTON, "apply_button")
            if not clicked:
                return self._make_result(
                    job_id, ApplicationStatus.SKIPPED,
                    error_message="Apply button not found — likely requires auth",
                )

            await self._random_delay(1.5, 3.0)
            await self._wait_for_navigation()

            # 3. Check for external ATS redirect
            current_url = self.page.url
            if _ATS_REDIRECT_PATTERNS.search(current_url):
                await self._emit_step("Redirected to external ATS -- skipping for re-dispatch")
                return self._make_result(
                    job_id, ApplicationStatus.SKIPPED,
                    error_message=f"Redirected to external ATS: {current_url}",
                )

            # 4. Multi-step form loop (modal or inline)
            for step in range(1, MAX_STEPS + 1):
                await self._emit_step(f"Processing form step {step}")
                await self._random_delay(0.5, 1.0)

                # Check for captcha between steps
                if await self._has_captcha():
                    return self._make_result(
                        job_id, ApplicationStatus.FAILED,
                        error_message="Captcha appeared during application flow",
                    )

                # Fill form fields on this step
                await self._fill_current_form(
                    user_profile=user_profile,
                    resume_text=resume_text,
                    cover_letter=cover_letter,
                    job_title=job.title,
                    job_company=job.company,
                    resume_file_path=resume_file_path,
                )

                # Upload resume if file input exists
                if resume_file_path:
                    await self._upload_resume(resume_file_path)

                await self._random_delay(0.5, 1.0)

                # Try Submit first (final step)
                if await self._click_selector(SUBMIT_BUTTON, "submit_button", timeout=2000):
                    await self._emit_step("Clicked Submit")
                    await self._wait_for_navigation()
                    break

                # Try Next/Continue (intermediate step)
                if await self._click_selector(NEXT_BUTTON, "next_button", timeout=2000):
                    await self._emit_step("Clicked Next/Continue")
                    await self._random_delay(0.5, 1.0)
                    continue

                # No navigation button -- stuck
                logger.warning("No Next/Submit button found at step %d", step)
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message=f"Stuck at step {step} -- no navigation button found",
                )
            else:
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message=f"Exceeded {MAX_STEPS} steps without submitting",
                )

            # 5. Post-submit checks (verification, captcha, confirmation, failure)
            await self._random_delay(1.0, 2.0)
            return await self._post_submit_check(job_id, cover_letter)

        except Exception as exc:
            logger.exception("Glassdoor apply failed for job %s", job_id)
            return self._make_result(
                job_id, ApplicationStatus.FAILED,
                error_message=str(exc),
            )

    # ------------------------------------------------------------------
    # Glassdoor-specific helpers
    # ------------------------------------------------------------------

    async def _has_captcha(self) -> bool:
        """Check for PerimeterX bot-detection captcha."""
        try:
            el = await self.page.query_selector(CAPTCHA_SELECTOR)
            return el is not None
        except Exception:
            return False
