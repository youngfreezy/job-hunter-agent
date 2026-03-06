"""Greenhouse Applier -- handles single-page forms at boards.greenhouse.io.

Greenhouse applications are typically a single page: click Apply, fill the form
(name, email, phone, resume, cover letter, custom questions), and submit.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from backend.shared.models.schemas import ApplicationResult, ApplicationStatus, JobListing

from .base import BaseApplier

logger = logging.getLogger(__name__)

_APPLY_SELECTORS = [
    "a#apply_button",
    'a:has-text("Apply for this job")',
    'button:has-text("Apply for this job")',
    'a:has-text("Apply Now")',
    'button:has-text("Apply Now")',
]

_SUBMIT_SELECTORS = [
    'input[type="submit"]',
    'button:has-text("Submit Application")',
    'button:has-text("Submit application")',
    'button[type="submit"]',
]

_FORM_SELECTORS = [
    "form#application_form",
    'form[action*="applications"]',
    "form",
]


class GreenhouseApplier(BaseApplier):
    PLATFORM = "greenhouse"

    async def apply(
        self,
        job: JobListing,
        user_profile: Dict[str, str],
        resume_text: str,
        cover_letter: str,
        resume_file_path: Optional[str] = None,
    ) -> ApplicationResult:
        # Step 1: Click "Apply for this job" button
        await self._emit_step("Looking for Greenhouse Apply button...")
        clicked = await self._click_selector(_APPLY_SELECTORS, "apply_button", timeout=5000)
        if clicked:
            await self._random_delay(1.0, 2.0)
            await self._wait_for_navigation(timeout=15000)

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
            logger.warning("Greenhouse: no application form found")
            return self._make_result(
                job.id, ApplicationStatus.SKIPPED,
                error_message="No Greenhouse application form found",
            )

        # Step 3: Fill the form
        await self._emit_step("Filling Greenhouse application form...")
        fill_result = await self._fill_current_form(
            user_profile=user_profile,
            resume_text=resume_text,
            cover_letter=cover_letter,
            job_title=job.title,
            job_company=job.company,
            resume_file_path=resume_file_path,
        )

        # Step 4: Upload resume
        if resume_file_path:
            await self._emit_step("Uploading resume...")
            await self._upload_resume(resume_file_path)
            await self._random_delay(0.5, 1.0)

        # Step 5: Submit the application
        await self._emit_step("Submitting application...")
        await self._random_delay(0.5, 1.0)
        submitted = await self._click_selector(_SUBMIT_SELECTORS, "submit_button", timeout=5000)

        if not submitted:
            return self._make_result(
                job.id, ApplicationStatus.FAILED,
                error_message="Could not find Greenhouse submit button",
            )

        await self._random_delay(3.0, 5.0)
        await self._wait_for_navigation(timeout=15000)

        # Step 6: Take post-submit screenshot for verification
        try:
            import os, tempfile
            screenshot_dir = os.path.join(tempfile.gettempdir(), "jobhunter_screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)
            safe_name = f"{job.company}_{job.title}".replace(" ", "_").replace("/", "_")[:60]
            screenshot_path = os.path.join(screenshot_dir, f"{safe_name}_submitted.png")
            await self.page.screenshot(path=screenshot_path, full_page=True)
            logger.info("Post-submit screenshot saved: %s", screenshot_path)
        except Exception:
            logger.debug("Screenshot capture failed", exc_info=True)

        # Step 7: Check for verification code prompt
        if await self._detect_verification_prompt():
            verified = await self._handle_verification()
            if not verified:
                return self._make_result(
                    job.id, ApplicationStatus.FAILED,
                    error_message="Verification code required but not provided in time",
                )
            await self._random_delay(1.0, 2.0)
            await self._wait_for_navigation()

        # Step 8: Detect confirmation
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
                error_message=f"Greenhouse detected: {failure}",
            )

        # Submit was clicked but no confirmation detected — report honestly as FAILED
        logger.warning("Greenhouse: submit clicked but no confirmation detected — FAILED")
        await self._emit_step("Submission not confirmed — form may have validation errors.")
        return self._make_result(
            job.id, ApplicationStatus.FAILED,
            error_message="Submit clicked but no confirmation page detected",
        )
