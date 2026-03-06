"""ZipRecruiter apply flow.

Handles the 1-Click Apply (instant submit) and multi-step form variants.
Dismisses the signup/email gate modal that often appears before the apply
button is accessible.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from backend.shared.models.schemas import ApplicationStatus, JobListing

from .base import BaseApplier

logger = logging.getLogger(__name__)

# -- Selector groups --------------------------------------------------------

CLOSE_MODAL = [
    'button[aria-label="Close"]',
    'button:has-text("\u00d7")',
    'button.modal-close',
    'button[aria-label="close"]',
]

APPLY_BUTTON = [
    'button:has-text("1-Click Apply")',
    'button:has-text("Apply")',
    'a:has-text("1-Click Apply")',
    'a:has-text("Apply")',
]

SUBMIT_BUTTON = [
    'button:has-text("Submit")',
    'button[type="submit"]',
    'button:has-text("Submit Application")',
]

# Indicators that the 1-Click path completed instantly
_ONE_CLICK_CONFIRM_KEYWORDS = [
    "applied", "application sent", "you applied",
]


class ZipRecruiterApplier(BaseApplier):
    """Applies to jobs via ZipRecruiter 1-Click or multi-step form."""

    PLATFORM = "ziprecruiter"

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
            # 1. Dismiss signup/email gate modal
            await self._dismiss_gate_modal()
            await self._random_delay(0.5, 1.0)

            # 2. Click Apply button
            await self._emit_step("Clicking Apply button")
            clicked = await self._click_selector(APPLY_BUTTON, "apply_button")
            if not clicked:
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message="Apply button not found on page",
                )

            await self._random_delay(1.5, 2.5)
            await self._wait_for_navigation()

            # 3. Check if 1-Click Apply completed instantly
            if await self._detect_one_click_success():
                await self._emit_step("1-Click Apply completed")
                return self._make_result(
                    job_id, ApplicationStatus.SUBMITTED,
                    cover_letter_used=cover_letter,
                )

            # 4. Multi-step form flow
            for step in range(1, 5):
                await self._emit_step(f"Processing form step {step}")
                await self._random_delay(0.5, 1.0)

                # Fill form fields
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

                # Try Submit
                if await self._click_selector(SUBMIT_BUTTON, "submit_button", timeout=3000):
                    await self._emit_step("Clicked Submit")
                    await self._wait_for_navigation()
                    break

                # No submit button -- may be stuck or page changed
                logger.warning("No Submit button found at step %d", step)
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message=f"Stuck at step {step} -- no Submit button found",
                )
            else:
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message="Exceeded max steps without submitting",
                )

            # 5. Detect confirmation
            await self._random_delay(1.0, 2.0)
            if await self._detect_confirmation():
                await self._emit_step("Application submitted successfully")
                return self._make_result(
                    job_id, ApplicationStatus.SUBMITTED,
                    cover_letter_used=cover_letter,
                )

            # Submit clicked but no explicit confirmation -- optimistic success
            return self._make_result(
                job_id, ApplicationStatus.SUBMITTED,
                cover_letter_used=cover_letter,
            )

        except Exception as exc:
            logger.exception("ZipRecruiter apply failed for job %s", job_id)
            return self._make_result(
                job_id, ApplicationStatus.FAILED,
                error_message=str(exc),
            )

    # ------------------------------------------------------------------
    # ZipRecruiter-specific helpers
    # ------------------------------------------------------------------

    async def _dismiss_gate_modal(self) -> None:
        """Dismiss the signup/email gate modal that often blocks the page."""
        # Try Escape key first
        try:
            await self.page.keyboard.press("Escape")
            await self._random_delay(0.3, 0.6)
        except Exception:
            pass

        # Then try close button selectors
        try:
            await self._click_selector(CLOSE_MODAL, "close_modal", timeout=2000)
        except Exception:
            pass

    async def _detect_one_click_success(self) -> bool:
        """Check if the 1-Click Apply completed without a form."""
        try:
            text = await self.page.evaluate("() => document.body.innerText.toLowerCase()")
            for kw in _ONE_CLICK_CONFIRM_KEYWORDS:
                if kw in text:
                    logger.info("1-Click success detected: '%s'", kw)
                    return True
        except Exception:
            pass
        # Also check the generic confirmation keywords
        return await self._detect_confirmation()
