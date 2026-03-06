"""Workday Applier -- handles multi-step wizard at *.myworkdayjobs.com.

Workday applications use a multi-step wizard: click Apply, then iterate through
pages filling forms and clicking Next until a Submit button appears. Uses
data-automation-id attributes extensively. Max 10 steps to avoid infinite loops.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from backend.shared.models.schemas import ApplicationResult, ApplicationStatus, JobListing

from .base import BaseApplier

logger = logging.getLogger(__name__)

MAX_STEPS = 10

_APPLY_SELECTORS = [
    'a[data-automation-id="jobPostingApplyButton"]',
    'button[data-automation-id="jobPostingApplyButton"]',
    'button:has-text("Apply")',
    'a:has-text("Apply")',
]

_NEXT_SELECTORS = [
    'button[data-automation-id="bottom-navigation-next-button"]',
    'button:has-text("Next")',
    'button:has-text("Continue")',
    'button:has-text("Save and Continue")',
]

_SUBMIT_SELECTORS = [
    'button[data-automation-id="submit"]',
    'button:has-text("Submit")',
    'button:has-text("Submit Application")',
    'button[type="submit"]',
]


class WorkdayApplier(BaseApplier):
    PLATFORM = "workday"

    async def apply(
        self,
        job: JobListing,
        user_profile: Dict[str, str],
        resume_text: str,
        cover_letter: str,
        resume_file_path: Optional[str] = None,
    ) -> ApplicationResult:
        # Step 1: Click the Apply button
        await self._emit_step("Looking for Workday Apply button...")
        clicked = await self._click_selector(_APPLY_SELECTORS, "apply_button", timeout=5000)
        if not clicked:
            return self._make_result(
                job.id, ApplicationStatus.SKIPPED,
                error_message="Could not find Workday Apply button",
            )

        await self._random_delay(1.5, 2.5)
        await self._wait_for_navigation()

        # Step 2: Multi-step wizard loop
        resume_uploaded = False

        for step in range(MAX_STEPS):
            await self._emit_step(f"Filling wizard step {step + 1}...")

            # Fill the current step's form
            fill_result = await self._fill_current_form(
                user_profile=user_profile,
                resume_text=resume_text,
                cover_letter=cover_letter,
                job_title=job.title,
                job_company=job.company,
                resume_file_path=resume_file_path,
            )

            # Upload resume if file input is visible and not yet uploaded
            if resume_file_path and not resume_uploaded:
                uploaded = await self._upload_resume(resume_file_path)
                if uploaded:
                    resume_uploaded = True
                    await self._emit_step("Resume uploaded, waiting for parsing...")
                    await self._random_delay(2.5, 4.0)  # Workday auto-parses resumes

            await self._random_delay(0.5, 1.0)

            # Try Submit first (appears on the final step)
            submitted = await self._click_selector(_SUBMIT_SELECTORS, "submit_button", timeout=3000)
            if submitted:
                await self._random_delay(1.5, 3.0)
                await self._wait_for_navigation()

                if await self._detect_confirmation():
                    await self._emit_step("Application submitted!")
                    return self._make_result(
                        job.id, ApplicationStatus.SUBMITTED,
                        cover_letter_used=cover_letter,
                    )

                # Check for failure after submit attempt
                failure = await self._detect_failure()
                if failure:
                    return self._make_result(
                        job.id, ApplicationStatus.FAILED,
                        error_message=f"Workday detected after submit: {failure}",
                    )

                # Submit clicked, no confirmation -- optimistic success
                logger.info("Workday: submit clicked, no confirmation -- assuming success")
                await self._emit_step("Application submitted (no explicit confirmation).")
                return self._make_result(
                    job.id, ApplicationStatus.SUBMITTED,
                    cover_letter_used=cover_letter,
                )

            # Try Next button to advance the wizard
            has_next = await self._click_selector(_NEXT_SELECTORS, "next_button", timeout=3000)
            if has_next:
                await self._random_delay(1.0, 2.0)
                await self._wait_for_navigation()
                continue

            # No Submit or Next -- check if already on confirmation page
            if await self._detect_confirmation():
                await self._emit_step("Application submitted!")
                return self._make_result(
                    job.id, ApplicationStatus.SUBMITTED,
                    cover_letter_used=cover_letter,
                )

            # Stuck -- no actionable button found
            logger.warning("Workday: no Next or Submit button at step %d", step + 1)
            break

        # Exhausted max steps or got stuck
        failure = await self._detect_failure()
        if failure:
            return self._make_result(
                job.id, ApplicationStatus.FAILED,
                error_message=f"Workday detected: {failure}",
            )

        return self._make_result(
            job.id, ApplicationStatus.FAILED,
            error_message=f"Workday wizard did not complete within {MAX_STEPS} steps",
        )
