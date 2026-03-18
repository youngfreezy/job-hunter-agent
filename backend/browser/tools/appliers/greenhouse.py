# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Greenhouse ATS applier — multi-step form with Next/Submit buttons."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from backend.browser.tools.appliers.base import BaseApplier
from backend.shared.models.schemas import (
    ApplicationErrorCategory,
    ApplicationResult,
    ApplicationStatus,
    JobListing,
)

logger = logging.getLogger(__name__)

# Greenhouse-specific selectors (ranked by reliability)
_APPLY_BUTTON = [
    "a#apply_button",
    'a[href*="/apply"]',
    'button:has-text("Apply")',
    'a:has-text("Apply for this job")',
    'a:has-text("Apply Now")',
]

_NEXT_BUTTON = [
    'button:has-text("Next")',
    'button[data-action="next"]',
    'input[type="submit"][value*="Next"]',
    'button:has-text("Continue")',
]

_SUBMIT_BUTTON = [
    'input[type="submit"]',
    'button[type="submit"]',
    'button:has-text("Submit Application")',
    'button:has-text("Submit")',
]

MAX_FORM_PAGES = 5


class GreenhouseApplier(BaseApplier):
    """Apply to jobs on boards.greenhouse.io via Playwright form filling."""

    PLATFORM = "greenhouse"

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
            # Step 1: Click the Apply button (if on job detail page)
            await self._emit_step("Looking for Apply button...")
            # Check if we're already on the application form
            has_form = await self.page.query_selector('form[action*="apply"], form[id*="application"]')
            if not has_form:
                clicked = await self._click_selector(_APPLY_BUTTON, "apply_button", timeout=5000)
                if not clicked:
                    # Maybe we're already on the form page
                    has_form = await self.page.query_selector("form")
                    if not has_form:
                        return self._make_result(
                            job_id, ApplicationStatus.FAILED,
                            error_message="Could not find Apply button or application form",
                        )
                await self._random_delay(1.0, 2.0)
                await self._wait_for_navigation()

            # Step 2: Multi-page form loop
            for page_num in range(1, MAX_FORM_PAGES + 1):
                await self._emit_step(f"Filling form page {page_num}...")

                # Fill current form page
                result = await self._fill_current_form(
                    user_profile=user_profile,
                    resume_text=resume_text,
                    cover_letter=cover_letter,
                    job_title=job.title,
                    job_company=job.company,
                    resume_file_path=resume_file_path,
                )

                await self._random_delay(0.5, 1.0)

                # Try clicking Next (multi-step form)
                next_clicked = await self._click_selector(_NEXT_BUTTON, "next_button", timeout=3000)
                if next_clicked:
                    await self._random_delay(1.0, 2.0)
                    await self._wait_for_navigation()
                    continue

                # No Next button — proactively solve CAPTCHA before Submit.
                # Greenhouse uses reCAPTCHA Enterprise (invisible). The iframe
                # loads after page idle, so wait a moment for it to appear.
                from backend.browser.tools.captcha_solver import solve_captcha
                await self._emit_step("Solving CAPTCHA...")
                await asyncio.sleep(3)  # wait for reCAPTCHA iframe to load
                solved = await solve_captcha(self.page)
                if solved:
                    logger.info("CAPTCHA pre-solved before submit click")
                await self._random_delay(1.0, 2.0)

                await self._emit_step("Submitting application...")
                submit_clicked = await self._click_selector(_SUBMIT_BUTTON, "submit_button", timeout=5000)
                if submit_clicked:
                    await self._random_delay(3.0, 5.0)
                    await self._wait_for_navigation(timeout=15000)

                    # If submit button still visible, try programmatic form.submit()
                    still_visible = await self.page.evaluate("""() => {
                        const buttons = [...document.querySelectorAll('button, input[type="submit"]')];
                        const submitBtn = buttons.find(b =>
                            b.textContent.toLowerCase().includes('submit') && b.offsetParent !== null
                        );
                        return !!submitBtn;
                    }""")
                    if still_visible:
                        logger.info("Submit button still visible after click — trying form.submit()")
                        await self.page.evaluate("""() => {
                            const form = document.querySelector('form');
                            if (form) form.submit();
                        }""")
                        await self._random_delay(3.0, 5.0)
                        await self._wait_for_navigation(timeout=15000)

                    # Check for validation errors — if present, re-fill and retry once
                    has_errors = await self.page.evaluate("""() => {
                        return [...document.querySelectorAll(
                            '.field--error, [class*="error-message"], [class*="field-error"], .field_with_errors'
                        )].some(el => el.offsetParent !== null)
                    }""")
                    if has_errors:
                        await self._emit_step("Fixing validation errors and resubmitting...")
                        await self._fill_current_form(
                            user_profile=user_profile,
                            resume_text=resume_text,
                            cover_letter=cover_letter,
                            job_title=job.title,
                            job_company=job.company,
                            resume_file_path=resume_file_path,
                        )
                        await self._random_delay(1.0, 2.0)
                        await self._click_selector(_SUBMIT_BUTTON, "submit_button", timeout=5000)
                        await self._random_delay(3.0, 5.0)
                        await self._wait_for_navigation(timeout=15000)

                    break

                # Neither Next nor Submit found
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message="Could not find Next or Submit button",
                )

            # Step 3: Post-submit check
            await self._capture_screenshot(job)
            return await self._post_submit_check(job_id, cover_letter)

        except Exception as exc:
            logger.error("Greenhouse apply failed for %s: %s", job.title, exc, exc_info=True)
            return self._make_result(
                job_id, ApplicationStatus.FAILED,
                error_message=f"Greenhouse apply error: {str(exc)[:200]}",
            )
