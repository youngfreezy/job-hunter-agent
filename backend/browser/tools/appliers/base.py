"""BaseApplier -- abstract base class for all platform-specific job appliers.

Provides shared helpers for clicking selectors (with DB-ranked fallback),
filling forms via form_filler, detecting confirmation pages, uploading
resumes, and emitting SSE progress events.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.browser.tools.apply_selectors import (
    get_top_selectors,
    record_failure,
    record_success,
)
from backend.browser.tools.form_filler import (
    analyse_form,
    extract_form_fields,
    fill_form,
)
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import (
    ApplicationResult,
    ApplicationStatus,
    JobListing,
)

logger = logging.getLogger(__name__)

_CONFIRM_KEYWORDS = [
    "submitted", "success", "thank you", "thanks for applying",
    "application received", "confirmation", "congratulations",
    "application has been submitted", "applied successfully",
]

_FAILURE_KEYWORDS = [
    "404", "not found", "page not found", "captcha",
    "unable to complete", "login required", "sign in",
    "access denied", "blocked",
]


class BaseApplier(ABC):
    """Abstract base for platform-specific job application handlers."""

    PLATFORM: str = "unknown"

    def __init__(self, page: Any, session_id: str) -> None:
        self.page = page
        self.session_id = session_id
        self._step_count = 0
        self._start_time = time.monotonic()

    @abstractmethod
    async def apply(
        self,
        job: JobListing,
        user_profile: Dict[str, str],
        resume_text: str,
        cover_letter: str,
        resume_file_path: Optional[str] = None,
    ) -> ApplicationResult:
        """Execute the full application flow."""
        ...

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def _emit_step(self, description: str) -> None:
        """Emit an SSE progress event."""
        self._step_count += 1
        await emit_agent_event(self.session_id, "application_progress", {
            "step": description,
            "step_count": self._step_count,
            "platform": self.PLATFORM,
        })

    async def _click_selector(
        self,
        hardcoded: List[str],
        step_type: str,
        timeout: int = 5000,
    ) -> bool:
        """Try DB-ranked selectors first, then hardcoded. Records success/failure.

        Returns True if a selector was clicked, False otherwise.
        """
        db_selectors = get_top_selectors(self.PLATFORM, step_type, limit=3)
        all_selectors = db_selectors + [s for s in hardcoded if s not in db_selectors]

        for sel in all_selectors:
            try:
                el = await self.page.wait_for_selector(sel, timeout=timeout, state="visible")
                if el:
                    await el.scroll_into_view_if_needed()
                    await self._random_delay(0.2, 0.5)
                    await el.click()
                    record_success(self.PLATFORM, step_type, sel)
                    logger.info("Clicked %s via %s", step_type, sel)
                    return True
            except Exception:
                record_failure(self.PLATFORM, step_type, sel)
                continue

        logger.warning("No selector matched for %s/%s", self.PLATFORM, step_type)
        return False

    async def _fill_current_form(
        self,
        user_profile: Dict[str, str],
        resume_text: str,
        cover_letter: str,
        job_title: str,
        job_company: str,
        resume_file_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extract fields from current page, send to Claude, fill via Playwright."""
        await self._emit_step("Analyzing form fields...")

        fields = await extract_form_fields(self.page)
        if not fields:
            return {"filled": 0, "skipped": 0, "errors": ["No form fields found"]}

        instructions = await analyse_form(
            fields=fields,
            resume_text=resume_text,
            cover_letter=cover_letter,
            job_title=job_title,
            job_company=job_company,
        )

        await self._emit_step(f"Filling {len(instructions)} fields...")

        result = await fill_form(
            page=self.page,
            instructions=instructions,
            resume_file_path=resume_file_path,
        )

        logger.info("Form fill: %d filled, %d skipped, %d errors",
                     result["filled"], result["skipped"], len(result["errors"]))
        return result

    async def _detect_confirmation(self) -> bool:
        """Check if current page shows a real submission confirmation.

        Strict verification — only returns True when we have strong evidence
        the application was accepted.  Never matches single keywords in job
        description text (previous version false-positived on 'success' in h1/h2).
        """
        try:
            result = await self.page.evaluate("""() => {
                const text = document.body.innerText.toLowerCase();
                const url = window.location.href.toLowerCase();

                // NEGATIVE: submit button still visible means form didn't go through
                const submitVisible = !!(
                    document.querySelector('button[type="submit"]')?.offsetParent ||
                    document.querySelector('input[type="submit"]')?.offsetParent
                );
                // NEGATIVE: validation errors present
                const hasErrors = [...document.querySelectorAll(
                    '.field--error, [class*="error-message"], [class*="field-error"]'
                )].some(el => el.offsetParent !== null);

                // Confirmation-specific elements (NOT generic h1/h2/headings)
                const confirmSels = [
                    '[class*="flash--success"]', '[class*="confirmation"]',
                    '[class*="thank-you"]', '[class*="success-message"]',
                    '[class*="application-confirmation"]',
                ];
                let confirmElText = '';
                for (const sel of confirmSels) {
                    document.querySelectorAll(sel).forEach(el => {
                        if (el.offsetParent !== null) {
                            confirmElText += ' ' + el.textContent.toLowerCase();
                        }
                    });
                }

                // URL change to a confirmation page
                const urlConfirm = url.includes('thank') || url.includes('confirm') ||
                                   url.includes('/submitted');

                return {
                    text: text.substring(0, 3000),
                    confirmElText,
                    submitVisible,
                    hasErrors,
                    urlConfirm,
                };
            }""")

            submit_visible = result.get("submitVisible", True)
            has_errors = result.get("hasErrors", False)
            confirm_el_text = result.get("confirmElText", "")
            text = result.get("text", "")
            url_confirm = result.get("urlConfirm", False)

            # Hard negatives — form didn't submit
            if has_errors:
                logger.info("Confirmation: validation errors present — NOT confirmed")
                return False
            if submit_visible:
                logger.info("Confirmation: submit button still visible — NOT confirmed")
                return False

            # URL redirected to confirmation page
            if url_confirm:
                logger.info("Confirmation: URL indicates success")
                return True

            # Multi-word phrases that only appear in real confirmation messages
            _SAFE_PHRASES = [
                "application has been submitted", "thanks for applying",
                "thank you for applying", "application received",
                "successfully submitted", "we have received your application",
                "your application has been received",
            ]
            for phrase in _SAFE_PHRASES:
                if phrase in text:
                    logger.info("Confirmation detected (phrase): '%s'", phrase)
                    return True

            # Confirmation-specific elements only
            for kw in ["submitted", "received", "thank you"]:
                if kw in confirm_el_text:
                    logger.info("Confirmation detected (confirm element): '%s'", kw)
                    return True

        except Exception:
            pass
        return False

    async def _detect_failure(self) -> Optional[str]:
        """Check if current page shows a failure indicator."""
        try:
            text = await self.page.evaluate("() => document.body.innerText.toLowerCase()")
            for kw in _FAILURE_KEYWORDS:
                if kw in text:
                    return kw
        except Exception:
            pass
        return None

    async def _upload_resume(self, file_path: str) -> bool:
        """Find a file input and upload the resume."""
        try:
            file_input = await self.page.query_selector('input[type="file"]')
            if file_input:
                await file_input.set_input_files(file_path)
                logger.info("Resume uploaded via file input")
                return True
        except Exception as exc:
            logger.warning("Resume upload failed: %s", exc)
        return False

    async def _random_delay(self, min_s: float = 0.5, max_s: float = 1.5) -> None:
        """Human-like delay."""
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def _wait_for_navigation(self, timeout: int = 10000) -> None:
        """Wait for page to settle after a click that triggers navigation."""
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=timeout)
        except Exception:
            pass  # timeout is acceptable, page may not navigate

    def _elapsed(self) -> int:
        return int(time.monotonic() - self._start_time)

    def _make_result(
        self,
        job_id: str,
        status: ApplicationStatus,
        error_message: Optional[str] = None,
        cover_letter_used: Optional[str] = None,
    ) -> ApplicationResult:
        return ApplicationResult(
            job_id=job_id,
            status=status,
            error_message=error_message,
            cover_letter_used=cover_letter_used,
            duration_seconds=self._elapsed(),
            submitted_at=datetime.utcnow() if status == ApplicationStatus.SUBMITTED else None,
        )
