"""LinkedIn Easy Apply applier.

Handles the LinkedIn Easy Apply modal flow: click Apply, fill multi-step
forms, and submit. The heavy lifting (field extraction + Claude-powered
filling) is delegated to _fill_current_form / form_filler.py.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from backend.shared.models.schemas import ApplicationStatus, JobListing

from .base import BaseApplier

logger = logging.getLogger(__name__)

# -- Selector groups --------------------------------------------------------

APPLY_BUTTON = [
    "button.jobs-apply-button",
    'button:has-text("Easy Apply")',
]

NEXT_BUTTON = [
    'button[aria-label="Continue to next step"]',
    'button:has-text("Next")',
]

REVIEW_BUTTON = [
    'button[aria-label="Review your application"]',
    'button:has-text("Review")',
]

SUBMIT_BUTTON = [
    'button[aria-label="Submit application"]',
    'button:has-text("Submit application")',
]

CLOSE_MODAL = [
    'button[aria-label="Dismiss"]',
]

MODAL_CONTAINER = [
    "div.jobs-easy-apply-modal",
    'div[class*="jobs-easy-apply"]',
]

MAX_STEPS = 8


class LinkedInApplier(BaseApplier):
    """Applies to jobs via LinkedIn Easy Apply."""

    PLATFORM = "linkedin"

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
            # 1. Click Easy Apply button
            await self._emit_step("Clicking Easy Apply button")
            clicked = await self._click_selector(APPLY_BUTTON, "apply_button")
            if not clicked:
                return self._make_result(
                    job_id, ApplicationStatus.SKIPPED,
                    error_message="Easy Apply button not found — likely requires auth",
                )

            await self._random_delay(1.0, 2.0)

            # 2. Wait for modal to appear
            modal_visible = await self._wait_for_modal()
            if not modal_visible:
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message="Easy Apply modal did not open",
                )

            # 3. Multi-step form loop
            for step in range(1, MAX_STEPS + 1):
                await self._emit_step(f"Processing form step {step}")
                await self._random_delay(0.5, 1.0)

                # Fill whatever form fields are on this step
                await self._fill_current_form(
                    user_profile=user_profile,
                    resume_text=resume_text,
                    cover_letter=cover_letter,
                    job_title=job.title,
                    job_company=job.company,
                    resume_file_path=resume_file_path,
                )

                # Upload resume if a file input is present
                if resume_file_path:
                    await self._upload_resume(resume_file_path)

                await self._random_delay(0.5, 1.0)

                # Try Submit first (final step)
                if await self._click_selector(SUBMIT_BUTTON, "submit_button", timeout=2000):
                    await self._emit_step("Clicked Submit application")
                    await self._wait_for_navigation()
                    break

                # Try Review (pre-submit step)
                if await self._click_selector(REVIEW_BUTTON, "review_button", timeout=2000):
                    await self._emit_step("Clicked Review")
                    await self._random_delay(0.5, 1.0)
                    continue

                # Try Next (intermediate step)
                if await self._click_selector(NEXT_BUTTON, "next_button", timeout=2000):
                    await self._emit_step("Clicked Next")
                    await self._random_delay(0.5, 1.0)
                    continue

                # No navigation button found -- may be stuck
                logger.warning("No Next/Review/Submit button found at step %d", step)
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message=f"Stuck at step {step} -- no navigation button found",
                )
            else:
                # Exhausted MAX_STEPS without submitting
                await self._dismiss_modal()
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message=f"Exceeded {MAX_STEPS} steps without submitting",
                )

            # 4. Detect confirmation
            await self._random_delay(1.0, 2.0)
            if await self._detect_confirmation():
                await self._emit_step("Application submitted successfully")
                return self._make_result(
                    job_id, ApplicationStatus.SUBMITTED,
                    cover_letter_used=cover_letter,
                )

            # No confirmation text but submit was clicked — FAILED
            return self._make_result(
                job_id, ApplicationStatus.FAILED,
                error_message="Submit clicked but no confirmation detected",
            )

        except Exception as exc:
            logger.exception("LinkedIn apply failed for job %s", job_id)
            await self._dismiss_modal()
            return self._make_result(
                job_id, ApplicationStatus.FAILED,
                error_message=str(exc),
            )

    # ------------------------------------------------------------------
    # LinkedIn-specific helpers
    # ------------------------------------------------------------------

    async def _wait_for_modal(self, timeout: int = 5000) -> bool:
        """Wait for the Easy Apply modal to become visible."""
        for sel in MODAL_CONTAINER:
            try:
                await self.page.wait_for_selector(sel, timeout=timeout, state="visible")
                return True
            except Exception:
                continue
        return False

    async def _dismiss_modal(self) -> None:
        """Try to close the Easy Apply modal to leave a clean state."""
        try:
            await self._click_selector(CLOSE_MODAL, "close_modal", timeout=2000)
        except Exception:
            pass
