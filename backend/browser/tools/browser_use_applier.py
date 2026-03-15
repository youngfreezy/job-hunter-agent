"""Browser-Use Applier -- LLM-driven job application via browser-use.

Replaces hardcoded CSS selectors with an AI agent that dynamically
analyses the page and figures out what to click, fill, and submit.

Supports two modes:
  1. Local/headless: launches a fresh browser (default)
  2. Extension CDP: connects to user's real Chrome via CDP relay
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.shared.event_bus import emit_agent_event
from backend.shared.llm import build_browser_use_llm
from backend.shared.models.schemas import (
    ApplicationErrorCategory,
    ApplicationResult,
    ApplicationStatus,
    JobListing,
)

logger = logging.getLogger(__name__)


def _build_task_prompt(
    job: JobListing,
    resume_text: str,
    cover_letter: str,
    user_profile: Dict[str, str],
    is_extension: bool = False,
) -> str:
    """Build a natural-language task for browser-use.

    When ``is_extension`` is True, the prompt assumes the user is already
    logged in (their real browser) and adjusts guidance accordingly.
    """
    # Fetch ATS-specific tips if available
    ats_tips = ""
    try:
        from backend.browser.tools.apply_selectors import get_ats_tips
        tips = get_ats_tips(job.url)
        if tips:
            ats_tips = f"\n\nATS-SPECIFIC TIPS:\n{tips}"
    except Exception:
        pass

    # Referral source
    referral = "jobhunteragent.com"

    auth_guidance = (
        "You are operating in the user's real browser — they may already be logged in. "
        "If you see a logged-in dashboard or profile, proceed directly to the application form. "
        "Do NOT log out or switch accounts."
        if is_extension
        else "If you encounter a login wall, STOP and report 'auth_required'."
    )

    return f"""You are applying for a job on behalf of an applicant. Here is your mission:

1. Navigate to the job page at {job.url}
2. Find and click the "Apply", "Easy Apply", or "Submit Application" button.
   - On LinkedIn: click "Easy Apply" to open the modal, then complete each step by clicking "Next", filling required fields, and finally clicking "Submit application" or "Review" then "Submit".
   - On external ATS sites (Workday, Greenhouse, Lever, etc.): fill out the application form normally.
3. Fill ALL required form fields using the applicant info below.
4. If there is a file upload for resume/CV, use the upload_resume tool.
5. If there is a cover letter text field, paste the cover letter below.
6. If there is a 'How did you hear about us' or referral source field, enter: '{referral}'.
7. Review for completeness, then submit.
8. Confirm you see a success/thank-you/confirmation page.

APPLICANT INFO:
- Full Name: {user_profile.get('name', 'N/A')}
- Email: x_email
- Phone: x_phone
- Location: {user_profile.get('location', 'N/A')}
- LinkedIn: {user_profile.get('linkedin_url', 'N/A')}
- GitHub: {user_profile.get('github_url', 'N/A')}
- Portfolio: {user_profile.get('portfolio_url', 'N/A')}

RESUME:
{resume_text[:4000]}

COVER LETTER:
{cover_letter[:2000]}

RULES:
- Only use information provided above. Do NOT fabricate experience or details.
- For any required field where you do not have data, use a reasonable default:
  - Salary: "Negotiable"
  - Start date: "Immediately"
  - Work authorization: "Yes"
  - Sponsorship required: "No"
  - Willing to relocate: "Yes"
  - Other free-text: write a brief plausible answer
- NEVER leave a required field empty.
- {auth_guidance}
- If you hit a CAPTCHA that blocks progress, report 'captcha_detected' and stop.
- If the job listing is expired or no longer available, report 'job_expired' and stop.
- Stay focused on completing this one application. Do not navigate away.
- For multi-step modals (like LinkedIn Easy Apply), complete ALL steps before reporting done.
{ats_tips}"""


async def apply_with_browser_use(
    job: JobListing,
    resume_text: str,
    cover_letter: str,
    user_profile: Dict[str, str],
    session_id: str,
    resume_file_path: Optional[str] = None,
    browser: Optional[Any] = None,
    cdp_url: Optional[str] = None,
) -> ApplicationResult:
    """Apply for a job using browser-use's AI agent.

    The agent dynamically navigates the page, finds form fields, fills them,
    and submits — no hardcoded selectors needed.

    Args:
        cdp_url: If provided, connect to an existing Chrome instance via CDP
                 (Chrome Extension mode). The user's browser with existing auth.
        browser: Reuse an existing browser-use Browser instance.
    """
    from browser_use import Agent, BrowserSession, ActionResult, Tools

    start_time = time.monotonic()
    is_extension = cdp_url is not None

    task = _build_task_prompt(job, resume_text, cover_letter, user_profile, is_extension)

    # Sensitive data — browser-use sees placeholders, substitutes real values at action time
    sensitive_data: Dict[str, str] = {}
    if user_profile.get("email"):
        sensitive_data["x_email"] = user_profile["email"]
    if user_profile.get("phone"):
        sensitive_data["x_phone"] = user_profile["phone"]

    # Browser session setup
    owns_browser = browser is None and cdp_url is None
    browser_session = None

    if cdp_url:
        # Extension mode: connect to user's real Chrome via CDP relay
        browser_session = BrowserSession(cdp_url=cdp_url)
        logger.info("browser-use connecting via CDP extension for %s", job.id)
    elif browser is None:
        from backend.shared.config import settings
        browser_session = BrowserSession(headless=settings.BROWSER_HEADLESS)
    else:
        # Legacy: passed a Browser object
        browser_session = browser

    # Custom tool for resume upload
    tools = Tools()
    if resume_file_path:
        @tools.action(description="Upload the applicant's resume/CV PDF to a file input on the page")
        async def upload_resume(browser_session) -> ActionResult:
            try:
                page = await browser_session.must_get_current_page()
                file_inputs = await page.query_selector_all('input[type="file"]')
                for fi in file_inputs:
                    await fi.set_input_files(resume_file_path)
                    return ActionResult(extracted_content="Resume uploaded successfully")
                return ActionResult(error="No file input found on the page")
            except Exception as e:
                return ActionResult(error=f"Resume upload failed: {e}")

    llm = build_browser_use_llm(max_tokens=8192, temperature=0.0)
    # Step callback for SSE progress
    step_count = 0

    async def on_step_end(agent_instance):
        nonlocal step_count
        step_count += 1
        try:
            actions = agent_instance.history.model_actions()
            thoughts = agent_instance.history.model_thoughts()
            latest_action = str(actions[-1])[:300] if actions else "thinking..."
            latest_thought = str(thoughts[-1])[:200] if thoughts else ""

            await emit_agent_event(session_id, "application_browser_action", {
                "job_id": job.id,
                "step": step_count,
                "action": latest_action,
                "thought": latest_thought,
                "mode": "extension" if is_extension else "headless",
            })
        except Exception:
            logger.debug("SSE emission failed in on_step_end", exc_info=True)

    # Build agent
    agent_kwargs: Dict[str, Any] = {
        "task": task,
        "llm": llm,
        "browser_session": browser_session,
        "max_actions_per_step": 1,
        "use_vision": True,
        "max_failures": 3,
        "tools": tools,
    }
    if sensitive_data:
        agent_kwargs["sensitive_data"] = sensitive_data
    if resume_file_path:
        agent_kwargs["available_file_paths"] = [resume_file_path]

    agent = Agent(**agent_kwargs)

    try:
        mode_label = "extension" if is_extension else "headless"
        await emit_agent_event(session_id, "application_progress", {
            "job_id": job.id,
            "step": f"Filling application for {job.title} at {job.company} ({mode_label})...",
        })

        result = await agent.run(max_steps=30, on_step_end=on_step_end)

        duration = int(time.monotonic() - start_time)

        # Check success via AgentHistoryList
        is_success = result.is_successful()
        final_text = str(result.final_result() or "")
        final_lower = final_text.lower()

        # Check for failure indicators FIRST — override is_successful()
        failure_keywords = [
            "404", "not found", "page could not be found", "no longer available",
            "expired", "removed", "impossible", "unable to complete",
            "cannot apply", "couldn't apply", "could not apply",
            "no application form", "login wall", "captcha",
            "auth_required", "job_expired", "captcha_detected",
        ]
        has_failure = any(kw in final_lower for kw in failure_keywords)
        if has_failure:
            is_success = False

        # Login wall / auth required → SKIPPED (not a real failure)
        auth_keywords = ["login wall", "login required", "sign in to apply",
                         "log in to apply", "create an account", "sign up to apply",
                         "auth_required"]
        is_auth_wall = any(kw in final_lower for kw in auth_keywords)

        # CAPTCHA → report for user intervention (extension mode)
        captcha_keywords = ["captcha", "recaptcha", "captcha_detected"]
        is_captcha = any(kw in final_lower for kw in captcha_keywords)

        # Job expired
        expired_keywords = ["job_expired", "no longer available", "expired", "removed"]
        is_expired = any(kw in final_lower for kw in expired_keywords)

        # Success keywords fallback
        if not is_success and not has_failure:
            success_keywords = [
                "submitted", "success", "thank you", "application complete",
                "applied", "confirmation",
            ]
            is_success = any(kw in final_lower for kw in success_keywords)

        if is_success:
            logger.info(
                "browser-use applied to %s at %s (mode=%s, steps=%d, duration=%ds)",
                job.title, job.company, mode_label, step_count, duration,
            )
            return ApplicationResult(
                job_id=job.id,
                status=ApplicationStatus.SUBMITTED,
                cover_letter_used=cover_letter,
                submitted_at=datetime.now(timezone.utc),
                duration_seconds=duration,
            )
        elif is_auth_wall:
            logger.info("browser-use hit auth wall for %s — skipping", job.id)
            return ApplicationResult(
                job_id=job.id,
                status=ApplicationStatus.SKIPPED,
                error_message="auth_required",
                error_category=ApplicationErrorCategory.AUTH_REQUIRED,
                duration_seconds=duration,
            )
        elif is_captcha:
            if is_extension:
                # In extension mode, emit event so user can solve it
                await emit_agent_event(session_id, "application_captcha_detected", {
                    "job_id": job.id,
                    "message": "CAPTCHA detected — please solve it in your browser",
                })
            return ApplicationResult(
                job_id=job.id,
                status=ApplicationStatus.FAILED,
                error_message="captcha_detected",
                error_category=ApplicationErrorCategory.CAPTCHA,
                duration_seconds=duration,
            )
        elif is_expired:
            return ApplicationResult(
                job_id=job.id,
                status=ApplicationStatus.SKIPPED,
                error_message="job_expired",
                error_category=ApplicationErrorCategory.JOB_EXPIRED,
                duration_seconds=duration,
            )
        else:
            error_msg = final_text[:500] if final_text else "No success confirmation detected"
            logger.warning("browser-use did not confirm success for %s", job.id)
            return ApplicationResult(
                job_id=job.id,
                status=ApplicationStatus.FAILED,
                error_message=error_msg,
                cover_letter_used=cover_letter,
                duration_seconds=duration,
            )

    except ConnectionError as exc:
        duration = int(time.monotonic() - start_time)
        logger.warning("Extension disconnected during application for %s: %s", job.id, exc)
        return ApplicationResult(
            job_id=job.id,
            status=ApplicationStatus.FAILED,
            error_message="extension_disconnected",
            error_category=ApplicationErrorCategory.UNKNOWN,
            duration_seconds=duration,
        )

    except Exception as exc:
        duration = int(time.monotonic() - start_time)
        error_str = str(exc).lower()

        # Detect extension-specific errors
        if "target closed" in error_str or "tab_closed" in error_str:
            logger.warning("Tab closed by user for %s", job.id)
            return ApplicationResult(
                job_id=job.id,
                status=ApplicationStatus.FAILED,
                error_message="tab_closed_by_user",
                duration_seconds=duration,
            )

        logger.exception("browser-use agent failed for %s", job.id)
        return ApplicationResult(
            job_id=job.id,
            status=ApplicationStatus.FAILED,
            error_message=f"browser-use error: {exc}",
            duration_seconds=duration,
        )
    finally:
        if owns_browser and browser_session:
            try:
                await browser_session.close()
            except Exception:
                pass
