# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Indeed applier — Indeed's own "Apply now" flow on a logged-in context.

Only meaningful in Browserbase mode with a persisted Indeed Context (the
user signed in once via Settings -> Browserbase -> "Sign in to Indeed").
The application node routes an indeed.com job here only when such a
Context is available; without one the job is skipped as auth_required
before any navigation happens.

SELECTORS ARE UNVERIFIED.  Nobody has confirmed the selectors below against
Indeed's live DOM from this code base yet (the rule in project-memory.md
forbids inventing selectors silently).  They are the repo's existing seed
selectors from apply_selectors.py plus the obvious text matches, and they
may well be wrong.  Every step therefore fails loudly: when no selector in
a group matches, the result is FAILED with the group and its selectors in
error_message and failure_step, never a quiet "no form found" skip.

TODO(unverified-selectors): verify each entry in _APPLY_BUTTON,
_CONTINUE_BUTTON, _SUBMIT_BUTTON and _SIGNED_OUT against the live Indeed
Apply flow with a logged-in Browserbase context, then drop this notice.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from backend.browser.tools.appliers.base import BaseApplier
from backend.shared.application_rules import ApplicationParked
from backend.shared.models.schemas import (
    ApplicationErrorCategory,
    ApplicationResult,
    ApplicationStatus,
    JobListing,
)

logger = logging.getLogger(__name__)

SELECTORS_VERIFIED = False  # flip only after a live-DOM check (see module docstring)

# TODO(unverified-selectors): the "Apply now" control on an indeed.com/viewjob page.
_APPLY_BUTTON: List[str] = [
    "#indeedApplyButton",
    "button.jobsearch-IndeedApplyButton",
    'button:has-text("Apply now")',
]

# TODO(unverified-selectors): the per-step "Continue" control of the Indeed Apply wizard.
_CONTINUE_BUTTON: List[str] = [
    'button[data-testid="continue-button"]',
    'button:has-text("Continue")',
]

# TODO(unverified-selectors): the final submit control of the Indeed Apply wizard.
_SUBMIT_BUTTON: List[str] = [
    'button:has-text("Submit your application")',
    'button[data-testid="submit-button"]',
]

# TODO(unverified-selectors): controls that only appear when the context is NOT signed in.
_SIGNED_OUT: List[str] = [
    'a[href*="secure.indeed.com/account/login"]',
    'a:has-text("Sign in")',
]

MAX_WIZARD_STEPS = 8


class IndeedApplier(BaseApplier):
    """Drive Indeed Apply (the multi-step wizard) on a logged-in Indeed context."""

    PLATFORM = "indeed"

    def _fail(
        self,
        job_id: str,
        *,
        step: str,
        message: str,
        category: ApplicationErrorCategory = ApplicationErrorCategory.FORM_NAVIGATION,
    ) -> ApplicationResult:
        """A loud failure: names the step and, for selector misses, the unverified group."""
        logger.error("Indeed applier failed at %s: %s", step, message)
        result = self._make_result(job_id, ApplicationStatus.FAILED, error_message=message)
        result.error_category = category
        result.failure_step = step
        result.ats_type = self.PLATFORM
        return result

    def _selector_miss(self, job_id: str, group: str, selectors: List[str], step: str) -> ApplicationResult:
        verified = "verified" if SELECTORS_VERIFIED else "UNVERIFIED against the live DOM"
        return self._fail(
            job_id,
            step=step,
            message=(
                f"Indeed applier: no match for {group} selectors ({verified}; "
                f"TODO(unverified-selectors) in appliers/indeed.py): {selectors}"
            ),
        )

    async def _signed_out(self) -> bool:
        url = (self.page.url or "").lower() if hasattr(self.page, "url") else ""
        if "secure.indeed.com" in url and "login" in url:
            return True
        for sel in _SIGNED_OUT:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    return True
            except Exception:
                continue
        return False

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
            if not SELECTORS_VERIFIED:
                logger.warning(
                    "Indeed applier running with UNVERIFIED selectors for %s; "
                    "failures will name the selector group (see appliers/indeed.py)",
                    job.title,
                )

            # Step 0: the persisted context must actually be signed in.
            if await self._signed_out():
                return self._fail(
                    job_id, step="page_load", category=ApplicationErrorCategory.AUTH_REQUIRED,
                    message="Indeed applier: page shows the signed-out state; the Indeed Context "
                            "is not logged in (re-run Settings -> Browserbase -> Sign in to Indeed)",
                )

            # Step 1: open the Indeed Apply wizard.
            await self._emit_step("Opening Indeed Apply...")
            if not await self._click_selector(_APPLY_BUTTON, "apply_button", timeout=8000):
                return self._selector_miss(job_id, "apply_button", _APPLY_BUTTON, step="page_load")
            await self._random_delay(1.5, 3.0)
            await self._wait_for_navigation()

            # Step 2: the wizard. Fill whatever the current step shows, then Continue;
            # when Continue is gone, look for the final submit.
            for step_num in range(1, MAX_WIZARD_STEPS + 1):
                await self._emit_step(f"Indeed Apply step {step_num}...")
                await self._fill_current_form(
                    user_profile=user_profile,
                    resume_text=resume_text,
                    cover_letter=cover_letter,
                    job_title=job.title,
                    job_company=job.company,
                    resume_file_path=resume_file_path,
                )
                await self._random_delay(0.5, 1.2)

                if await self._click_selector(_CONTINUE_BUTTON, "next_button", timeout=4000):
                    await self._random_delay(1.0, 2.0)
                    await self._wait_for_navigation()
                    continue

                await self._emit_step("Submitting Indeed application...")
                if not await self._click_selector(_SUBMIT_BUTTON, "submit_button", timeout=6000):
                    return self._fail(
                        job_id, step="submit",
                        message=(
                            f"Indeed applier: neither a Continue nor a Submit control matched on "
                            f"wizard step {step_num} (UNVERIFIED selectors, TODO(unverified-selectors) "
                            f"in appliers/indeed.py): continue={_CONTINUE_BUTTON} submit={_SUBMIT_BUTTON}"
                        ),
                    )
                await self._random_delay(2.0, 4.0)
                await self._wait_for_navigation(timeout=15000)
                await self._capture_screenshot(job)
                result = await self._post_submit_check(job_id, cover_letter)
                result.ats_type = self.PLATFORM
                return result

            return self._fail(
                job_id, step="form_fill",
                message=f"Indeed applier: wizard did not reach a submit control within {MAX_WIZARD_STEPS} steps",
            )

        except ApplicationParked:
            raise  # BaseApplier.run() turns this into a SKIPPED result
        except Exception as exc:
            logger.error("Indeed apply failed for %s: %s", job.title, exc, exc_info=True)
            return self._fail(
                job_id, step="form_fill", category=ApplicationErrorCategory.UNKNOWN,
                message=f"Indeed apply error: {str(exc)[:200]}",
            )
