# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""LinkedIn Easy Apply applier.

Handles the LinkedIn Easy Apply modal flow: click Apply, fill multi-step
forms, and submit. The heavy lifting (field extraction + Claude-powered
filling) is delegated to _fill_current_form / form_filler.py.

When Easy Apply is not available, attempts to find and return the external
apply URL so the caller can redirect to the appropriate ATS applier.
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
    "button.apply-button",
    "button.sign-up-modal__outlet",
    'button:has-text("Easy Apply")',
    'button:has-text("Apply")',
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
            # Scroll to bottom to ensure apply button loads (LinkedIn lazy-loads)
            try:
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await self._random_delay(1.0, 2.0)
                await self.page.evaluate("window.scrollTo(0, 0)")
                await self._random_delay(0.5, 1.0)
            except Exception:
                pass
            clicked = await self._click_selector(APPLY_BUTTON, "apply_button", timeout=10000)
            if not clicked:
                # Easy Apply not found — try to find external apply link
                external_url = await self._find_external_url()
                if external_url:
                    logger.info(
                        "LinkedIn: no Easy Apply, found external URL: %s",
                        external_url,
                    )
                    return self._make_result(
                        job_id, ApplicationStatus.SKIPPED,
                        error_message=f"external_redirect:{external_url}",
                    )
                # Log what buttons are visible for debugging
                try:
                    debug = await self.page.evaluate("""() => {
                        const buttons = Array.from(document.querySelectorAll('button, a[href], input[type="submit"]'))
                            .filter(el => {
                                const t = (el.textContent || el.value || '').toLowerCase();
                                const c = (el.className || '').toLowerCase();
                                return t.includes('apply') || c.includes('apply') || c.includes('sign-up') || el.tagName === 'BUTTON';
                            })
                            .slice(0, 20)
                            .map(b => `${b.tagName}.${(b.className || '').substring(0,50)} | ${(b.textContent || b.value || '').trim().substring(0, 80)}`);
                        const title = document.title;
                        const url = window.location.href;
                        const bodySnippet = document.body.innerText.substring(0, 500);
                        return { buttons, title, url, bodySnippet };
                    }""")
                    logger.info("LinkedIn: page debug - title='%s' url='%s' buttons=%s", debug.get('title', '?'), debug.get('url', '?'), debug.get('buttons', []))
                except Exception:
                    pass
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

            # 4. Post-submit checks (verification, captcha, confirmation, failure)
            await self._random_delay(1.0, 2.0)
            return await self._post_submit_check(job_id, cover_letter)

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

    async def _find_external_url(self) -> str | None:
        """Scan the page for an external apply link (non-Easy-Apply).

        LinkedIn non-Easy-Apply jobs have an "Apply" button that links out
        to the company's ATS (Greenhouse, Lever, Workday, etc.).
        """
        from urllib.parse import urlparse, parse_qs, unquote

        _ATS_DOMAINS = [
            "greenhouse.io", "lever.co", "myworkdayjobs.com",
            "smartrecruiters.com", "icims.com", "jobvite.com",
            "ashbyhq.com", "bamboohr.com", "workable.com",
        ]

        try:
            links = await self.page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.href)
            }""")
            for href in (links or []):
                href_lower = href.lower()
                # LinkedIn externalApply redirect pattern
                if "externalapply" in href_lower:
                    try:
                        parsed = urlparse(href)
                        params = parse_qs(parsed.query)
                        if "url" in params:
                            decoded = unquote(params["url"][0])
                            if any(d in decoded.lower() for d in _ATS_DOMAINS):
                                return decoded
                    except Exception:
                        pass
                # Direct ATS link
                if any(d in href_lower for d in _ATS_DOMAINS):
                    return href
        except Exception:
            pass

        # Try clicking the non-Easy-Apply "Apply" button to reveal external link
        try:
            apply_btn = await self.page.query_selector(
                'a.apply-button, '
                'a[data-tracking-control-name*="apply"], '
                'a:has-text("Apply")'
            )
            if apply_btn:
                href = await apply_btn.get_attribute("href")
                if href:
                    href_lower = href.lower()
                    if "externalapply" in href_lower:
                        parsed = urlparse(href)
                        params = parse_qs(parsed.query)
                        if "url" in params:
                            return unquote(params["url"][0])
                    if any(d in href_lower for d in _ATS_DOMAINS):
                        return href
        except Exception:
            pass

        return None
