"""Browser-Use Applier -- LLM-driven job application via browser-use.

Replaces hardcoded CSS selectors with an AI agent that dynamically
analyses the page and figures out what to click, fill, and submit.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.shared.event_bus import emit_agent_event
from backend.shared.llm import build_browser_use_llm
from backend.shared.models.schemas import ApplicationResult, ApplicationStatus, JobListing

logger = logging.getLogger(__name__)


def _build_task_prompt(
    job: JobListing,
    resume_text: str,
    cover_letter: str,
    user_profile: Dict[str, str],
) -> str:
    """Build a natural-language task for browser-use."""
    return f"""You are applying for a job on behalf of an applicant. Here is your mission:

1. You are on the job page at {job.url}
2. Find and click the "Apply", "Easy Apply", or "Submit Application" button.
   - On LinkedIn: click "Easy Apply" to open the modal, then complete each step by clicking "Next", filling required fields, and finally clicking "Submit application" or "Review" then "Submit".
   - On external ATS sites (Workday, Greenhouse, Lever, etc.): fill out the application form normally.
3. Fill ALL required form fields using the applicant info below.
4. If there is a file upload for resume/CV, use the upload_resume tool.
5. If there is a cover letter text field, paste the cover letter below.
6. Review for completeness, then submit.
7. Confirm you see a success/thank-you/confirmation page.

APPLICANT INFO:
- Full Name: {user_profile.get('name', 'N/A')}
- Email: x_email
- Phone: x_phone
- Location: {user_profile.get('location', 'N/A')}

RESUME:
{resume_text[:3000]}

COVER LETTER:
{cover_letter[:2000]}

RULES:
- Only use information provided above. Do NOT fabricate experience or details.
- If a field asks for something not provided, skip it or select a reasonable default (e.g., "No" for sponsorship, earliest available start date).
- If you hit a CAPTCHA, stop and report it.
- You should already be logged in. If you encounter a login wall, report "login wall" and stop.
- Stay focused on completing this one application. Do not navigate away.
- For multi-step modals (like LinkedIn Easy Apply), complete ALL steps before reporting done.
"""


async def apply_with_browser_use(
    job: JobListing,
    resume_text: str,
    cover_letter: str,
    user_profile: Dict[str, str],
    session_id: str,
    resume_file_path: Optional[str] = None,
    browser: Optional[Any] = None,
) -> ApplicationResult:
    """Apply for a job using browser-use's AI agent.

    The agent dynamically navigates the page, finds form fields, fills them,
    and submits — no hardcoded selectors needed.

    Pass an existing ``browser`` to reuse across multiple applications (avoids
    2-5 s cold-start per call).  If *None*, a fresh instance is created and
    cleaned up after use.
    """
    from browser_use import Agent, Browser, ActionResult, Tools

    start_time = time.monotonic()

    task = _build_task_prompt(job, resume_text, cover_letter, user_profile)

    # Sensitive data — browser-use sees placeholders, substitutes real values at action time
    sensitive_data: Dict[str, str] = {}
    if user_profile.get("email"):
        sensitive_data["x_email"] = user_profile["email"]
    if user_profile.get("phone"):
        sensitive_data["x_phone"] = user_profile["phone"]

    # Reuse provided browser or create a new one
    owns_browser = browser is None
    if owns_browser:
        from backend.shared.config import settings

        browser = Browser(headless=settings.BROWSER_HEADLESS, disable_security=True)

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
            })
        except Exception:
            logger.debug("SSE emission failed in on_step_end", exc_info=True)

    # Build agent
    agent_kwargs: Dict[str, Any] = {
        "task": task,
        "llm": llm,
        "browser": browser,
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
        await emit_agent_event(session_id, "application_progress", {
            "job_id": job.id,
            "step": f"Filling out the application for {job.title} at {job.company}...",
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
        ]
        has_failure = any(kw in final_lower for kw in failure_keywords)
        if has_failure:
            is_success = False

        # Login wall / auth required → SKIPPED (not a real failure)
        auth_keywords = ["login wall", "login required", "sign in to apply",
                         "log in to apply", "create an account", "sign up to apply"]
        is_auth_wall = any(kw in final_lower for kw in auth_keywords)

        # Also check for success keywords in case is_successful is unreliable
        if not is_success and not has_failure:
            success_keywords = [
                "submitted", "success", "thank you", "application complete",
                "applied", "confirmation",
            ]
            is_success = any(kw in final_lower for kw in success_keywords)

        if is_success:
            logger.info(
                "browser-use applied to %s at %s (steps=%d, duration=%ds)",
                job.title, job.company, step_count, duration,
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
                duration_seconds=duration,
            )
        else:
            error_msg = "No success confirmation detected"
            logger.warning("browser-use did not confirm success for %s", job.id)
            return ApplicationResult(
                job_id=job.id,
                status=ApplicationStatus.FAILED,
                error_message=error_msg,
                cover_letter_used=cover_letter,
                duration_seconds=duration,
            )

    except Exception as exc:
        duration = int(time.monotonic() - start_time)
        logger.exception("browser-use agent failed for %s", job.id)
        return ApplicationResult(
            job_id=job.id,
            status=ApplicationStatus.FAILED,
            error_message=f"browser-use error: {exc}",
            duration_seconds=duration,
        )
    finally:
        if owns_browser:
            try:
                await browser.stop()
            except Exception:
                pass
