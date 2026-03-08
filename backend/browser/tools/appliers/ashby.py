# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Ashby Applier -- handles application forms at jobs.ashbyhq.com.

Ashby forms use a React-based system where each field fill triggers a
GraphQL mutation (ApiSetFormValue). File uploads via set_input_files cause
a stuck spinner in React state, so we reload the page after upload and
re-fill all fields before submitting.

Key strategy:
1. Fill form fields (triggers ApiSetFormValue for each)
2. Upload resume via set_input_files (triggers S3 upload)
3. Reload page to clear stuck React upload spinner
4. Re-fill ALL fields (IDs change after reload)
5. Click Yes/No toggle buttons (triggers ApiSetFormValue)
6. Remove any blocking toasts from DOM
7. Click Submit -> reCAPTCHA auto-passes in visible mode -> 200
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Dict, Optional

from backend.shared.models.schemas import ApplicationResult, ApplicationStatus, JobListing

from .base import BaseApplier

logger = logging.getLogger(__name__)

_SUBMIT_SELECTORS = [
    'button:has-text("Submit Application")',
    'button:has-text("Submit")',
    'button[type="submit"]',
    'input[type="submit"]',
]


class AshbyApplier(BaseApplier):
    PLATFORM = "ashby"

    async def apply(
        self,
        job: JobListing,
        user_profile: Dict[str, str],
        resume_text: str,
        cover_letter: str,
        resume_file_path: Optional[str] = None,
    ) -> ApplicationResult:
        # Step 1: Verify the application form is present
        await self._emit_step("Loading Ashby application form...")
        form_found = False
        for sel in ['input[name="_systemfield_name"]', 'input[type="text"]', 'textarea']:
            try:
                el = await self.page.wait_for_selector(sel, timeout=5000, state="visible")
                if el:
                    form_found = True
                    break
            except Exception:
                continue

        if not form_found:
            logger.warning("Ashby: no application form found")
            return self._make_result(
                job.id, ApplicationStatus.SKIPPED,
                error_message="No Ashby application form found",
            )

        # Step 2: Fill the form (first pass)
        await self._emit_step("Filling Ashby application form...")
        fill_result = await self._fill_current_form(
            user_profile=user_profile,
            resume_text=resume_text,
            cover_letter=cover_letter,
            job_title=job.title,
            job_company=job.company,
            resume_file_path=resume_file_path,
        )

        # Step 3: Handle radio buttons
        await self._fill_radio_buttons()

        # Step 4: Click Yes/No toggle buttons
        await self._click_yes_buttons()

        # Step 5: Upload resume
        if resume_file_path:
            await self._emit_step("Uploading resume...")
            uploaded = await self._upload_resume_ashby(resume_file_path)
            if uploaded:
                # Wait for S3 upload to complete
                await asyncio.sleep(3)

                # Reload page to clear the stuck React upload spinner
                await self._emit_step("Processing upload...")
                await self.page.reload(wait_until="domcontentloaded")
                await asyncio.sleep(3)

                # Re-fill form after reload (IDs change)
                await self._emit_step("Verifying form data...")
                await self._fill_current_form(
                    user_profile=user_profile,
                    resume_text=resume_text,
                    cover_letter=cover_letter,
                    job_title=job.title,
                    job_company=job.company,
                    resume_file_path=resume_file_path,
                )
                await self._fill_radio_buttons()
                await self._click_yes_buttons()

                # Re-upload resume
                await self._upload_resume_ashby(resume_file_path)
                await asyncio.sleep(2)

        # Step 6: Submit
        await self._emit_step("Submitting application...")
        await self._random_delay(0.5, 1.0)

        # Remove any blocking toasts before submit
        await self.page.evaluate("""() => {
            document.querySelectorAll('[class*="toast"], [class*="Toast"], [role="alert"]').forEach(t => t.remove());
            document.querySelectorAll('[class*="spinner"], [class*="Spinner"]').forEach(s => s.remove());
        }""")
        await asyncio.sleep(0.5)

        submitted = await self._click_selector(_SUBMIT_SELECTORS, "submit_button", timeout=5000)

        if not submitted:
            return self._make_result(
                job.id, ApplicationStatus.FAILED,
                error_message="Could not find Ashby submit button",
            )

        await self._random_delay(2.0, 4.0)
        await self._wait_for_navigation()

        # Step 7: Take screenshot
        await self._capture_screenshot(job)

        # Step 8: Post-submit checks (verification, captcha, confirmation, failure)
        return await self._post_submit_check(job.id, cover_letter)

    async def _fill_radio_buttons(self) -> None:
        """Check radio buttons (pick middle option for each group)."""
        try:
            radio_groups = await self.page.evaluate("""() => {
                const groups = new Set();
                document.querySelectorAll('input[type="radio"]').forEach(r => {
                    if (r.offsetParent !== null && r.name) groups.add(r.name);
                });
                return [...groups];
            }""")
            for name in radio_groups:
                radios = await self.page.query_selector_all(f'[name="{name}"]')
                if radios:
                    mid = len(radios) // 2
                    try:
                        await radios[mid].check(force=True)
                    except Exception:
                        pass
        except Exception:
            pass

    async def _click_yes_buttons(self) -> None:
        """Click visible Yes toggle buttons (common on Ashby forms)."""
        try:
            yes_buttons = await self.page.locator('button:has-text("Yes")').all()
            for btn in yes_buttons:
                if await btn.is_visible():
                    is_pressed = await btn.get_attribute("aria-pressed")
                    classes = await btn.get_attribute("class") or ""
                    if is_pressed != "true" and "active" not in classes.lower() and "selected" not in classes.lower():
                        await btn.click()
                        await asyncio.sleep(0.5)
        except Exception:
            pass

    async def _upload_resume_ashby(self, file_path: str) -> bool:
        """Upload resume to the Ashby Resume field (not the Autofill field)."""
        try:
            file_inputs = await self.page.query_selector_all('input[type="file"]')
            if not file_inputs:
                return False

            # Find the Resume field (not the autofill one)
            for fi in file_inputs:
                label = await fi.evaluate("""(el) => {
                    const parent = el.closest('[class*="field"], [class*="question"], [class*="section"]');
                    if (parent) {
                        const lbl = parent.querySelector('label, [class*="label"]');
                        if (lbl) return lbl.textContent.trim().toLowerCase();
                    }
                    return '';
                }""")
                if "resume" in label and "autofill" not in label:
                    await fi.set_input_files(file_path)
                    return True

            # Fallback: upload to last file input
            await file_inputs[-1].set_input_files(file_path)
            return True
        except Exception as e:
            logger.warning("Ashby resume upload failed: %s", e)
            return False
