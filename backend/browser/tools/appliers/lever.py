"""Lever Applier -- handles applications at jobs.lever.co.

Lever uses a single-page form: click Apply, the form scrolls into view with
resume upload, name, email, phone, URLs, cover letter, and custom questions.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from backend.shared.models.schemas import ApplicationResult, ApplicationStatus, JobListing

from .base import BaseApplier

logger = logging.getLogger(__name__)

_APPLY_SELECTORS = [
    "a.postings-btn",
    'a:has-text("Apply for this job")',
    'button:has-text("Apply for this job")',
    'a:has-text("Apply")',
    ".postings-btn-wrapper a",
]

_SUBMIT_SELECTORS = [
    'button.postings-btn[type="submit"]',
    'button:has-text("Submit application")',
    'button:has-text("Submit Application")',
    'button[type="submit"]',
]

_FORM_SELECTORS = [
    "form.application-form",
    'form[action*="applications"]',
    ".application-form",
]


class LeverApplier(BaseApplier):
    PLATFORM = "lever"

    async def apply(
        self,
        job: JobListing,
        user_profile: Dict[str, str],
        resume_text: str,
        cover_letter: str,
        resume_file_path: Optional[str] = None,
    ) -> ApplicationResult:
        # Step 1: Click "Apply for this job" button
        await self._emit_step("Looking for Lever Apply button...")
        clicked = await self._click_selector(_APPLY_SELECTORS, "apply_button", timeout=5000)
        if clicked:
            await self._random_delay(1.0, 2.0)
            await self._wait_for_navigation()

        # Step 2: Verify the form is present
        form_found = False
        for sel in _FORM_SELECTORS:
            try:
                el = await self.page.wait_for_selector(sel, timeout=3000, state="visible")
                if el:
                    form_found = True
                    break
            except Exception:
                continue

        if not form_found:
            logger.warning("Lever: no application form found")
            return self._make_result(
                job.id, ApplicationStatus.SKIPPED,
                error_message="No Lever application form found",
            )

        # Step 3: Upload resume first (Lever shows it at the top of the form)
        if resume_file_path:
            await self._emit_step("Uploading resume...")
            await self._upload_resume(resume_file_path)
            await self._random_delay(0.5, 1.0)

        # Step 4: Fill the form
        await self._emit_step("Filling Lever application form...")
        fill_result = await self._fill_current_form(
            user_profile=user_profile,
            resume_text=resume_text,
            cover_letter=cover_letter,
            job_title=job.title,
            job_company=job.company,
            resume_file_path=resume_file_path,
        )

        # Step 5: Submit the application
        await self._emit_step("Submitting application...")
        await self._random_delay(0.5, 1.0)
        submitted = await self._click_selector(_SUBMIT_SELECTORS, "submit_button", timeout=5000)

        if not submitted:
            return self._make_result(
                job.id, ApplicationStatus.FAILED,
                error_message="Could not find Lever submit button",
            )

        await self._random_delay(1.5, 3.0)
        await self._wait_for_navigation()

        # Step 6: Detect confirmation
        if await self._detect_confirmation():
            await self._emit_step("Application submitted!")
            return self._make_result(
                job.id, ApplicationStatus.SUBMITTED,
                cover_letter_used=cover_letter,
            )

        # Check for failure indicators
        failure = await self._detect_failure()
        if failure:
            return self._make_result(
                job.id, ApplicationStatus.FAILED,
                error_message=f"Lever detected: {failure}",
            )

        # Submit was clicked but no confirmation detected — FAILED
        logger.info("Lever: submit clicked, no confirmation detected -- FAILED")
        await self._emit_step("Application submitted (no explicit confirmation).")
        return self._make_result(
            job.id, ApplicationStatus.FAILED,
            error_message="Submit clicked but no confirmation detected",
        )
