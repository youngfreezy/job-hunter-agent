# Copyright (c) 2026 V2 Software LLC. All rights reserved.

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

from playwright.async_api import TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)


async def goto_with_retry(page: Any, url: str, *, max_retries: int = 2, **kwargs) -> None:
    """Navigate to *url* with retries on playwright timeout.

    Only retries the page.goto() call itself -- callers should use this
    instead of raw ``page.goto()`` for the initial navigation, NOT for
    wrapping entire form-fill flows.
    """
    for attempt in range(max_retries + 1):
        try:
            await page.goto(url, **kwargs)
            return
        except PlaywrightTimeout:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt + random.uniform(0, 1)
            logger.warning(
                "Navigation timeout (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                max_retries,
                wait,
                url[:120],
            )
            await asyncio.sleep(wait)

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

_VERIFICATION_KEYWORDS = [
    "verification code", "security code", "enter the code",
    "we sent a code", "check your email", "confirm your email",
    "one-time code", "otp", "2-factor", "two-factor",
    "enter code", "verify your identity", "verification email",
    "confirmation code", "confirm email", "email verification",
    "verify email", "access code", "code sent to",
    "enter the verification", "verify your email",
]


class BaseApplier(ABC):
    """Abstract base for platform-specific job application handlers."""

    PLATFORM: str = "unknown"

    def __init__(self, page: Any, session_id: str) -> None:
        self.page = page
        self.session_id = session_id
        self._step_count = 0
        self._start_time = time.monotonic()
        self._screenshot_path: Optional[str] = None
        self._current_company: str = ""

    async def run(
        self,
        job: JobListing,
        user_profile: Dict[str, str],
        resume_text: str,
        cover_letter: str,
        resume_file_path: Optional[str] = None,
    ) -> ApplicationResult:
        """Entry point — sets context then delegates to platform-specific apply()."""
        self._current_company = getattr(job, "company", "") or ""
        return await self.apply(
            job=job,
            user_profile=user_profile,
            resume_text=resume_text,
            cover_letter=cover_letter,
            resume_file_path=resume_file_path,
        )

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
                # Try wait_for_selector first, then direct query_selector (for below-fold buttons)
                el = None
                try:
                    el = await self.page.wait_for_selector(sel, timeout=timeout, state="visible")
                except Exception:
                    try:
                        el = await self.page.query_selector(sel)
                    except Exception:
                        pass
                if el:
                    try:
                        await el.scroll_into_view_if_needed()
                    except Exception:
                        pass
                    await self._random_delay(0.2, 0.5)
                    await el.click()
                    record_success(self.PLATFORM, step_type, sel)
                    logger.info("Clicked %s via %s", step_type, sel)
                    return True
            except Exception:
                record_failure(self.PLATFORM, step_type, sel)
                continue

        # Log visible buttons for debugging
        if step_type == "submit_button":
            try:
                buttons = await self.page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('button, input[type="submit"]'))
                        .slice(0, 15)
                        .map(b => `${b.tagName}.${b.className.substring(0,40)} | ${(b.textContent || b.value || '').trim().substring(0, 60)}`)
                }""")
                logger.info("Visible buttons when submit not found (%s): %s", self.PLATFORM, buttons)
            except Exception:
                pass
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
            user_profile=user_profile,
        )

        await self._emit_step(f"Filling {len(instructions)} fields...")

        result = await fill_form(
            page=self.page,
            instructions=instructions,
            resume_file_path=resume_file_path,
            session_id=self.session_id,
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

                const visibleButtons = [...document.querySelectorAll('button, input[type="submit"], input[type="button"]')]
                    .filter(el => el.offsetParent !== null)
                    .map(el => ((el.innerText || el.value || '') + '').toLowerCase().trim());
                // NEGATIVE: submit/apply controls still visible usually means form didn't go through.
                // Ignore unrelated buttons like "sign in", "back to job post", etc.
                // Only match form-specific submit buttons, NOT generic nav buttons like "Apply now"
                const submitVisible = visibleButtons.some(label =>
                    label === 'submit' ||
                    label === 'submit application' ||
                    label.includes('submit application') ||
                    label.includes('submit your application')
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
            logger.info("Confirmation check: submitVisible=%s hasErrors=%s urlConfirm=%s text_len=%d",
                        submit_visible, has_errors, url_confirm, len(text))

            # Hard negative — visible validation errors mean the form did not submit.
            if has_errors:
                logger.info("Confirmation: validation errors present — NOT confirmed")
                return False

            # URL redirected to confirmation page
            if url_confirm:
                logger.info("Confirmation: URL indicates success")
                return True

            # Multi-word phrases that only appear in real confirmation messages
            _SAFE_PHRASES = [
                "thanks for applying", "application submitted successfully",
                "application has been submitted",
                "thank you for applying", "application received",
                "successfully submitted", "we have received your application",
                "your application has been received",
                "we successfully received your application",
                "good news! we successfully received",
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

            if submit_visible:
                logger.info("Confirmation: submit/apply button still visible — NOT confirmed")
                return False

        except Exception:
            pass
        return False

    async def _has_recaptcha(self) -> bool:
        """Check for reCAPTCHA iframe or challenge on the page."""
        try:
            return await self.page.evaluate("""() => {
                const iframes = document.querySelectorAll('iframe[src*="recaptcha"], iframe[src*="hcaptcha"]');
                const divs = document.querySelectorAll('.g-recaptcha, [data-sitekey], #recaptcha');
                return iframes.length > 0 || divs.length > 0;
            }""")
        except Exception:
            return False

    async def _detect_failure(self) -> Optional[str]:
        """Check if current page shows a failure indicator or reCAPTCHA."""
        # Check for reCAPTCHA first (common on Greenhouse)
        if await self._has_recaptcha():
            return "captcha"
        try:
            text = await self.page.evaluate("() => document.body.innerText.toLowerCase()")
            for kw in _FAILURE_KEYWORDS:
                if kw in text:
                    return kw
        except Exception:
            pass
        return None

    async def _detect_verification_prompt(self) -> bool:
        """Check if current page is asking for a verification/security code."""
        try:
            text = await self.page.evaluate("() => document.body.innerText.toLowerCase().substring(0, 2000)")
            return any(kw in text for kw in _VERIFICATION_KEYWORDS)
        except Exception:
            return False

    async def _handle_verification(self) -> bool:
        """Try Gmail auto-extraction first, then fall back to manual entry.

        Returns True if verification was completed, False if timed out.
        """
        company = getattr(self, "_current_company", "")
        await self._emit_step(f"Verification code required — checking Gmail for code from {company or self.PLATFORM}...")

        # --- Phase 1: Gmail auto-extraction ---
        try:
            from backend.shared.gmail_client import poll_for_verification_code

            code = await poll_for_verification_code(
                session_id=self.session_id,
                company=company,
                platform=self.PLATFORM,
                max_wait=90,
                poll_interval=8,
            )
            if code:
                await self._emit_step(f"Found verification code — entering automatically")
                filled = await self._fill_verification_code(code)
                if filled:
                    await self._random_delay(0.5, 1.0)
                    # Try to submit the code
                    for btn_sel in [
                        "button[type='submit']",
                        "button:has-text('Verify')",
                        "button:has-text('Continue')",
                        "button:has-text('Submit')",
                        "button:has-text('Confirm')",
                    ]:
                        try:
                            btn = await self.page.query_selector(btn_sel)
                            if btn and await btn.is_visible():
                                await btn.click()
                                break
                        except Exception:
                            continue
                    await asyncio.sleep(3)
                    if not await self._detect_verification_prompt():
                        logger.info("Verification resolved via Gmail auto-extraction")
                        return True
                    logger.warning("Verification prompt still present after auto-fill — falling back to manual")
        except Exception as exc:
            logger.warning("Gmail auto-extraction failed: %s", exc)

        # --- Phase 2: Manual fallback ---
        # Check if Gmail token exists — if not (anonymous/free-trial user), skip
        # the 120s manual wait since there's no logged-in user to enter codes.
        from backend.shared.redis_client import redis_client as _redis
        try:
            has_gmail = await _redis.get_json(f"gmail_token:{self.session_id}")
        except Exception:
            has_gmail = None

        if not has_gmail:
            await self._emit_step("Verification code required but no email account connected — skipping this application.")
            await emit_agent_event(self.session_id, "verification_progress", {
                "agent": "applier",
                "message": "Skipped — email verification required. Sign up to enable auto-verification.",
            })
            logger.info("No Gmail token for session %s — skipping verification wait (anonymous user)", self.session_id)
            return False

        await self._emit_step("Could not auto-extract code — please enter it manually in the browser window.")
        await emit_agent_event(self.session_id, "verification_required", {
            "message": "A verification code was requested. Please check your email and enter the code in the browser window.",
            "platform": self.PLATFORM,
        })

        for _ in range(24):  # 24 * 5s = 120s
            await asyncio.sleep(5)
            if not await self._detect_verification_prompt():
                logger.info("Verification prompt resolved (manual)")
                return True

        logger.warning("Verification timed out after 120s")
        return False

    async def _post_submit_check(
        self,
        job_id: str,
        cover_letter: str = "",
    ) -> ApplicationResult:
        """Universal post-submit handler: verification → confirm → fail.

        Polls for confirmation up to 5 times (15s total) to handle AJAX
        form submissions that don't trigger page navigation.
        """

        # 1. Verification code prompt?
        if await self._detect_verification_prompt():
            verified = await self._handle_verification()
            if not verified:
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message="Verification code required but not provided in time",
                )
            await self._random_delay(1.0, 2.0)
            await self._wait_for_navigation()

        # 2. CAPTCHA check — try to solve via 2captcha if API key is set
        captcha_attempted = False
        if await self._has_recaptcha():
            captcha_attempted = True
            from backend.browser.tools.captcha_solver import solve_captcha
            solved = await solve_captcha(self.page)
            if solved:
                logger.info("CAPTCHA solved — re-clicking submit")
                # Re-click submit after CAPTCHA solved
                await self._click_selectors("submit_button")
                await asyncio.sleep(5)
            else:
                logger.info("CAPTCHA detected and unsolvable — submission blocked")
                return self._make_result(
                    job_id, ApplicationStatus.FAILED,
                    error_message="CAPTCHA unsolvable (2captcha failed)",
                )

        # 3. Poll for confirmation (AJAX submissions may take a moment)
        for attempt in range(5):
            if await self._detect_confirmation():
                await self._emit_step("Application submitted!")
                return self._make_result(
                    job_id, ApplicationStatus.SUBMITTED,
                    cover_letter_used=cover_letter,
                )
            if attempt < 4:
                await asyncio.sleep(3)

        # 4. Failure? (skip captcha check if we already solved it — DOM element persists)
        failure = await self._detect_failure()
        if failure:
            if failure == "captcha" and captcha_attempted:
                # CAPTCHA was solved but form still didn't submit — likely a
                # different issue (validation error, JS callback didn't fire)
                failure = "no_confirmation_after_captcha_solve"
            return self._make_result(
                job_id, ApplicationStatus.FAILED,
                error_message=f"{self.PLATFORM} detected: {failure}",
            )

        # 4. No signal
        return self._make_result(
            job_id, ApplicationStatus.FAILED,
            error_message=f"No confirmation detected on {self.PLATFORM}",
        )

    async def _fill_verification_code(self, code: str) -> bool:
        """Find a verification code input on the page and fill it."""
        selectors = [
            'input[autocomplete="one-time-code"]',
            'input[name*="code" i]',
            'input[name*="verification" i]',
            'input[name*="otp" i]',
            'input[inputmode="numeric"]',
            'input[type="tel"]',
            'input[name*="pin" i]',
        ]
        for sel in selectors:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    await el.fill(code)
                    logger.info("Filled verification code via selector: %s", sel)
                    return True
            except Exception:
                continue
        # Last resort: find any visible short text input that's empty
        try:
            inputs = await self.page.query_selector_all('input[type="text"], input:not([type])')
            for inp in inputs:
                if await inp.is_visible():
                    val = await inp.get_attribute("value") or ""
                    maxlen = await inp.get_attribute("maxlength") or ""
                    if not val and maxlen and int(maxlen) <= 10:
                        await inp.fill(code)
                        logger.info("Filled verification code via generic short input")
                        return True
        except Exception:
            pass
        logger.warning("Could not find a verification code input field")
        return False

    async def _upload_resume(self, file_path: str) -> bool:
        """Find a file input and upload the resume (decrypt if encrypted)."""
        try:
            file_input = await self.page.query_selector('input[type="file"]')
            if not file_input:
                return False

            if file_path.endswith(".enc"):
                from backend.shared.resume_crypto import decrypted_tempfile
                with decrypted_tempfile(file_path) as tmp_path:
                    await file_input.set_input_files(tmp_path)
            else:
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

    async def _capture_screenshot(self, job: "JobListing") -> Optional[str]:
        """Take a post-action screenshot and persist to Postgres."""
        try:
            png_bytes = await self.page.screenshot(full_page=True)
            from backend.shared.screenshot_store import store_screenshot_bytes
            row_id = store_screenshot_bytes(
                session_id=self.session_id,
                job_id=str(job.id),
                image_data=png_bytes,
            )
            if row_id:
                self._screenshot_path = f"/api/sessions/{self.session_id}/screenshots/{row_id}"
                logger.info("Screenshot stored in Postgres (id=%s)", row_id)
                return self._screenshot_path
        except Exception:
            logger.debug("Screenshot capture failed", exc_info=True)
        return None

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
            screenshot_url=self._screenshot_path,
            error_message=error_message,
            cover_letter_used=cover_letter_used,
            duration_seconds=self._elapsed(),
            submitted_at=datetime.utcnow() if status == ApplicationStatus.SUBMITTED else None,
        )
