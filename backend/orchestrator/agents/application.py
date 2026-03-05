"""Application Agent -- submits job applications via Playwright browser automation.

Uses real browser automation to:
1. Navigate to each approved job's application URL
2. Detect the ATS type (Workday, Greenhouse, Lever, etc.)
3. Query Neo4j for known ATS strategies (if available)
4. Create accounts when required (pausing for email verification)
5. Generate a tailored cover letter for each job
6. Analyse and fill application forms using Claude + FormFiller
7. Upload the resume file
8. Take a verification screenshot before submission
9. Submit the application
10. Record the result

"""

from __future__ import annotations

import asyncio
import base64
import logging
import random
import time
import uuid
from datetime import datetime, timezone
from functools import partial
from typing import Any, Dict, List, Optional

from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.config import get_settings
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import (
    ApplicationResult,
    ApplicationStatus,
    JobListing,
)

logger = logging.getLogger(__name__)

# Circuit-breaker threshold
MAX_CONSECUTIVE_FAILURES = 3


# ---------------------------------------------------------------------------
# Helpers -- lazy imports to avoid import-time failures when browser
# deps are not installed
# ---------------------------------------------------------------------------

async def _get_browser_manager():
    """Lazy-import and return a BrowserManager instance."""
    from backend.browser.manager import BrowserManager
    return BrowserManager()


async def _detect_ats(page: Any) -> str:
    """Detect the ATS type of the page."""
    from backend.browser.tools.ats_detector import detect_ats_type
    ats = await detect_ats_type(page)
    return ats.value


async def _query_neo4j_strategy(ats_type: str) -> Optional[str]:
    """Query Neo4j for a known ATS-filling strategy.

    Returns the strategy string, or None if Neo4j is not available or
    no strategy is found.
    """
    settings = get_settings()
    if not settings.NEO4J_URI:
        return None

    try:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        async with driver.session() as session:
            result = await session.run(
                "MATCH (s:ATSStrategy {ats_type: $ats_type}) "
                "RETURN s.strategy AS strategy LIMIT 1",
                ats_type=ats_type,
            )
            record = await result.single()
            await driver.close()

            if record:
                logger.info("Found Neo4j strategy for ATS %s", ats_type)
                return record["strategy"]
    except Exception:
        logger.debug("Neo4j strategy lookup failed for %s", ats_type, exc_info=True)

    return None


async def _record_result_to_neo4j(
    job_id: str,
    ats_type: str,
    success: bool,
) -> None:
    """Record an application result to Neo4j for learning."""
    settings = get_settings()
    if not settings.NEO4J_URI:
        return

    try:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        async with driver.session() as session:
            await session.run(
                "MERGE (r:ApplicationRecord {job_id: $job_id}) "
                "SET r.ats_type = $ats_type, r.success = $success, "
                "    r.timestamp = datetime()",
                job_id=job_id,
                ats_type=ats_type,
                success=success,
            )
        await driver.close()
    except Exception:
        logger.debug("Neo4j record write failed", exc_info=True)



def _find_job_in_state(job_id: str, state: JobHunterState) -> Optional[JobListing]:
    """Look up a JobListing by ID from discovered_jobs or scored_jobs."""
    # Check discovered_jobs
    for job in (state.get("discovered_jobs") or []):
        if job.id == job_id:
            return job
    # Check scored_jobs
    for scored in (state.get("scored_jobs") or []):
        if scored.job.id == job_id:
            return scored.job
    return None


# ---------------------------------------------------------------------------
# Intervention helpers
# ---------------------------------------------------------------------------


async def _wait_for_submit_approval(
    session_id: str,
    job_id: str,
    job: Any,
    page: Any,
    fields_filled: int = 0,
) -> str:
    """Pause before submit and wait for user to approve, skip, or take control.

    Emits a ``ready_to_submit`` SSE event with a pre-submit screenshot.
    Returns ``"submit"`` if approved, ``"skip"`` to skip this job.
    """
    # Capture pre-submit screenshot
    screenshot_b64 = None
    try:
        ss_bytes = await page.screenshot(type="jpeg", quality=70, full_page=True)
        screenshot_b64 = await asyncio.to_thread(
            lambda b: base64.b64encode(b).decode("utf-8"), ss_bytes
        )
    except Exception:
        pass

    await emit_agent_event(session_id, "ready_to_submit", {
        "job_id": job_id,
        "job_title": job.title if hasattr(job, "title") else str(job_id),
        "company": job.company if hasattr(job, "company") else "Unknown",
        "url": page.url,
        "fields_filled": fields_filled,
        "screenshot": screenshot_b64,
        "message": f"Ready to submit application for {job.title} at {job.company}. Review the form in the browser window and approve.",
    })

    logger.info("Waiting for submit approval for %s (session %s)...", job_id, session_id)

    try:
        import redis.asyncio as aioredis
        settings = get_settings()
        redis_client = aioredis.from_url(settings.REDIS_URL)

        approve_key = f"submit:approve:{session_id}"
        await redis_client.delete(approve_key)

        # Poll for approval (every 2s, max 10 minutes)
        for _ in range(300):
            result = await redis_client.get(approve_key)
            if result:
                decision = result.decode("utf-8") if isinstance(result, bytes) else str(result)
                logger.info("Submit decision for %s: %s", session_id, decision)
                await redis_client.delete(approve_key)
                await redis_client.close()
                return decision  # "submit" or "skip"
            await asyncio.sleep(2)

        await redis_client.close()
        logger.warning("Submit approval timeout for %s — skipping", session_id)
        return "skip"
    except Exception as exc:
        logger.warning("Submit approval wait failed: %s — auto-submitting", exc)
        return "submit"


async def _check_submission_confirmation(page: Any) -> bool:
    """Check if the page shows a submission confirmation after clicking submit.

    Looks for common confirmation indicators like 'thank you', 'application received',
    'successfully submitted', etc.
    """
    try:
        await page.wait_for_timeout(2000)  # Give page time to update

        # Check for common confirmation text patterns
        confirmation_patterns = [
            "thank you",
            "thanks for applying",
            "application received",
            "application submitted",
            "successfully submitted",
            "application has been submitted",
            "we received your application",
            "your application is complete",
            "congratulations",
            "application confirmation",
        ]

        page_text = (await page.inner_text("body")).lower()

        for pattern in confirmation_patterns:
            if pattern in page_text:
                return True

        # Check if URL changed to a confirmation/success page
        current_url = page.url.lower()
        url_indicators = ["thank", "confirm", "success", "complete", "submitted"]
        for indicator in url_indicators:
            if indicator in current_url:
                return True

        # Check for validation errors still visible
        error_selectors = [
            '[class*="error"]:visible',
            '[class*="alert-danger"]:visible',
            '[class*="validation"]:visible',
            '[role="alert"]:visible',
        ]
        for selector in error_selectors:
            try:
                errors = await page.query_selector_all(selector)
                if errors:
                    return False  # Validation errors present
            except Exception:
                pass

        return False
    except Exception:
        return False


async def _pause_for_intervention(
    session_id: str,
    job_id: str,
    job: Any,
    reason: str,
    page: Any = None,
    screenshot_b64: str | None = None,
) -> None:
    """Pause the agent and notify the user that intervention is needed.

    The agent will wait until the user resumes via the API.
    The browser stays open in headed mode so the user can interact directly.
    """
    logger.info("Agent paused for intervention: %s (job: %s)", reason, job_id)

    # Capture screenshot if not provided
    if not screenshot_b64 and page:
        try:
            ss_bytes = await page.screenshot(type="jpeg", quality=70)
            screenshot_b64 = await asyncio.to_thread(
                lambda b: base64.b64encode(b).decode("utf-8"), ss_bytes
            )
        except Exception:
            pass

    await emit_agent_event(session_id, "needs_intervention", {
        "job_id": job_id,
        "job_title": job.title if hasattr(job, 'title') else str(job_id),
        "company": job.company if hasattr(job, 'company') else "Unknown",
        "reason": reason,
        "screenshot": screenshot_b64,
        "message": f"Agent needs help with {job.title if hasattr(job, 'title') else job_id}: {reason}",
    })

    # Wait for user to resume — poll a Redis key
    try:
        import redis.asyncio as aioredis
        settings = get_settings()
        redis_client = aioredis.from_url(settings.REDIS_URL)

        resume_key = f"intervention:resume:{session_id}"
        # Clear any stale resume signal
        await redis_client.delete(resume_key)

        logger.info("Waiting for user intervention (key: %s)...", resume_key)

        # Poll for resume signal (check every 2 seconds, max 10 minutes)
        for _ in range(300):
            result = await redis_client.get(resume_key)
            if result:
                logger.info("User resumed intervention for session %s", session_id)
                await redis_client.delete(resume_key)
                break
            await asyncio.sleep(2)
        else:
            logger.warning("Intervention timeout for session %s (10 minutes)", session_id)

        await redis_client.close()
    except Exception as exc:
        logger.warning("Intervention wait failed: %s — continuing", exc)


# ---------------------------------------------------------------------------
# Playwright application
# ---------------------------------------------------------------------------

async def _apply_with_playwright(
    job_id: str,
    job: JobListing,
    state: JobHunterState,
    session_id: str,
) -> ApplicationResult:
    """Submit a real application using Playwright browser automation.

    Steps:
    1. Create browser context and navigate to application URL
    2. Detect ATS type
    3. Query Neo4j for strategy
    4. Create account if needed (pause for email verification via HITL)
    5. Generate tailored cover letter
    6. Analyse and fill the form
    7. Upload resume
    8. Take verification screenshot
    9. Submit
    10. Record result to Neo4j
    """
    start_time = time.monotonic()
    manager = await _get_browser_manager()
    ctx_id = None
    screenshot_url: Optional[str] = None
    ats_type_str = "unknown"

    try:
        await manager.start()
        ctx_id, context = await manager.new_context()

        # Import tools
        from backend.browser.anti_detect.stealth import apply_stealth
        from backend.browser.tools.form_filler import (
            analyse_form,
            extract_form_fields,
            fill_form,
        )
        from backend.browser.tools.cover_letter import generate_cover_letter
        from backend.browser.tools.account_creator import (
            create_account,
            detect_account_required,
        )
        from backend.browser.streaming.screenshot_streamer import ScreenshotStreamer

        page = await context.new_page()
        await apply_stealth(page)

        # Start screenshot streamer immediately so user can watch from the start
        streamer: Optional[ScreenshotStreamer] = None
        try:
            streamer = ScreenshotStreamer(session_id=session_id)
            await streamer.start(page)
            logger.info("Screenshot streamer started for %s (running=%s)", session_id, streamer._running)
        except Exception:
            logger.warning("Screenshot streamer failed to start for %s", session_id, exc_info=True)

        # Publish SSE: starting application
        await emit_agent_event(session_id, "application_start", {
            "job_id": job_id,
            "job_title": job.title,
            "company": job.company,
            "url": job.url,
        })

        # --- Step 1: Navigate to application URL ---
        logger.info("Navigating to application URL: %s", job.url)
        await page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(random.randint(2000, 4000))

        # --- Step 2: Detect ATS type ---
        ats_type_str = await _detect_ats(page)
        logger.info("Detected ATS: %s for %s at %s", ats_type_str, job.title, job.company)

        await emit_agent_event(session_id, "application_ats_detected", {
            "job_id": job_id,
            "ats_type": ats_type_str,
        })

        # --- Step 3: Query Neo4j for strategy ---
        ats_strategy = await _query_neo4j_strategy(ats_type_str)

        # --- Step 4: Account creation if needed ---
        needs_account = await detect_account_required(page)
        if needs_account:
            logger.info("Account creation required for %s", job.company)
            await emit_agent_event(session_id, "application_account_required", {
                "job_id": job_id,
                "company": job.company,
            })

            # Extract email from resume text for account creation
            resume_text = state.get("coached_resume") or state.get("resume_text", "")
            import re as _re
            email_match = _re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', resume_text)
            user_email = email_match.group(0) if email_match else None
            if not user_email:
                logger.warning("No email found in resume — skipping account creation")
                return ApplicationResult(
                    job_id=job_id,
                    status=ApplicationStatus.SKIPPED,
                    error_message="No email in resume — cannot create account",
                    duration_seconds=int(time.monotonic() - start_time),
                )

            # Extract name from first line of resume
            first_line = resume_text.strip().split("\n")[0].strip()
            name_parts = first_line.split()
            first_name = name_parts[0] if name_parts else ""
            last_name = name_parts[-1] if len(name_parts) > 1 else ""

            account_result = await create_account(
                page,
                email=user_email,
                password=f"Jh{uuid.uuid4().hex[:12]}!",
                first_name=first_name,
                last_name=last_name,
            )

            if account_result.needs_email_verification:
                logger.warning(
                    "Email verification required for %s -- marking as needing HITL",
                    job.company,
                )
                await emit_agent_event(session_id, "application_needs_verification", {
                    "job_id": job_id,
                    "company": job.company,
                    "message": "Email verification required. Please verify and resume.",
                })
                # Cannot proceed without verification -- skip this job
                return ApplicationResult(
                    job_id=job_id,
                    status=ApplicationStatus.SKIPPED,
                    error_message="Email verification required -- needs human intervention",
                    duration_seconds=int(time.monotonic() - start_time),
                )

            if not account_result.success:
                raise RuntimeError(
                    f"Account creation failed: {account_result.error}"
                )

        # --- Step 5: Generate tailored cover letter ---
        resume_text = state.get("coached_resume") or state.get("resume_text", "")
        cover_letter_template = state.get("cover_letter_template", "")

        cover_letter = await generate_cover_letter(
            job=job,
            resume_text=resume_text,
            template=cover_letter_template,
        )
        cover_letter_text = cover_letter.text

        await emit_agent_event(session_id, "application_cover_letter_ready", {
            "job_id": job_id,
            "cover_letter_preview": cover_letter_text[:200],
        })

        # --- Step 7: Analyse and fill form ---
        try:
            form_fields = await extract_form_fields(page)

            if form_fields:
                fill_instructions = await analyse_form(
                    fields=form_fields,
                    resume_text=resume_text,
                    cover_letter=cover_letter_text,
                    job_title=job.title,
                    job_company=job.company,
                    ats_strategy=ats_strategy,
                )

                # --- Step 8: Fill the form + upload resume ---
                resume_file = state.get("resume_file_path")
                fill_result = await fill_form(
                    page,
                    fill_instructions,
                    resume_file_path=resume_file,
                )

                logger.info(
                    "Form fill for %s: %d filled, %d skipped, %d errors",
                    job_id,
                    fill_result["filled"],
                    fill_result["skipped"],
                    len(fill_result["errors"]),
                )

                await emit_agent_event(session_id, "application_form_filled", {
                    "job_id": job_id,
                    "fields_filled": fill_result["filled"],
                    "fields_skipped": fill_result["skipped"],
                })

                # If there were fill errors, pause for intervention
                if fill_result["errors"]:
                    await _pause_for_intervention(
                        session_id=session_id,
                        job_id=job_id,
                        job=job,
                        reason=f"Form fill had {len(fill_result['errors'])} errors: {'; '.join(fill_result['errors'][:3])}",
                        page=page,
                    )
            else:
                logger.warning("No form fields found on page for %s", job_id)
                await _pause_for_intervention(
                    session_id=session_id,
                    job_id=job_id,
                    job=job,
                    reason="No form fields detected on the page. The page may need scrolling, clicking an 'Apply' button first, or requires a different approach.",
                    page=page,
                )
        except Exception as form_exc:
            logger.error("Form filling error for %s: %s", job_id, form_exc)
            await _pause_for_intervention(
                session_id=session_id,
                job_id=job_id,
                job=job,
                reason=f"Error during form filling: {str(form_exc)}",
                page=page,
            )

        # --- Step 9: Pre-submit confirmation gate ---
        submit_btn = await page.query_selector(
            'button[type="submit"], '
            'button:has-text("Submit"), '
            'button:has-text("Apply"), '
            'button:has-text("Submit Application"), '
            'input[type="submit"]'
        )

        fields_filled_count = fill_result["filled"] if 'fill_result' in dir() else 0
        submit_decision = await _wait_for_submit_approval(
            session_id=session_id,
            job_id=job_id,
            job=job,
            page=page,
            fields_filled=fields_filled_count,
        )

        if submit_decision == "skip":
            logger.info("User skipped submission for %s", job_id)
            if streamer:
                await streamer.stop()
            return ApplicationResult(
                job_id=job_id,
                status=ApplicationStatus.SKIPPED,
                error_message="Skipped by user before submission",
                duration_seconds=int(time.monotonic() - start_time),
            )

        # --- Step 10: Submit the application ---
        confirmation_ok = False
        if submit_btn:
            await submit_btn.click()
            await page.wait_for_timeout(random.randint(3000, 5000))

            # --- Post-submit confirmation check ---
            confirmation_ok = await _check_submission_confirmation(page)

            # Take screenshot AFTER submit (not before)
            try:
                post_screenshot_bytes = await page.screenshot(type="png", full_page=True)
                post_screenshot_b64 = await asyncio.to_thread(
                    lambda b: base64.b64encode(b).decode("utf-8"), post_screenshot_bytes
                )
                screenshot_url = f"data:image/png;base64,{post_screenshot_b64}"
            except Exception:
                logger.warning("Post-submit screenshot failed for %s", job_id)

            if confirmation_ok:
                logger.info("Application confirmed for %s at %s", job.title, job.company)
            else:
                logger.warning("No confirmation detected after submit for %s — may have failed", job_id)
                # Pause for user intervention
                await _pause_for_intervention(
                    session_id=session_id,
                    job_id=job_id,
                    job=job,
                    reason="No confirmation page detected after clicking submit. The form may have validation errors or require additional steps.",
                    screenshot_b64=post_screenshot_b64 if 'post_screenshot_b64' in dir() else None,
                    page=page,
                )
        else:
            logger.warning("No submit button found for %s", job_id)
            await _pause_for_intervention(
                session_id=session_id,
                job_id=job_id,
                job=job,
                reason="No submit button found on the page. The form may require scrolling or the page structure is different than expected.",
                page=page,
            )

        # --- Step 11: Stop streamer ---
        if streamer:
            await streamer.stop()

        # --- Step 12: Record result to Neo4j ---
        await _record_result_to_neo4j(job_id, ats_type_str, success=confirmation_ok)

        duration = int(time.monotonic() - start_time)

        if confirmation_ok:
            await emit_agent_event(session_id, "application_submitted", {
                "job_id": job_id,
                "job_title": job.title,
                "company": job.company,
            })

            return ApplicationResult(
                job_id=job_id,
                status=ApplicationStatus.SUBMITTED,
                screenshot_url=screenshot_url,
                cover_letter_used=cover_letter_text,
                submitted_at=datetime.now(timezone.utc),
                duration_seconds=duration,
            )
        else:
            await emit_agent_event(session_id, "application_failed", {
                "job_id": job_id,
                "job_title": job.title,
                "company": job.company,
                "error": "No submission confirmation detected",
            })

            return ApplicationResult(
                job_id=job_id,
                status=ApplicationStatus.FAILED,
                error_message="No submission confirmation detected",
                screenshot_url=screenshot_url,
                cover_letter_used=cover_letter_text,
                duration_seconds=duration,
            )

    except Exception as exc:
        duration = int(time.monotonic() - start_time)
        logger.exception("Playwright application failed for job %s", job_id)

        # Capture error screenshot so the user can see what went wrong
        error_screenshot_b64 = None
        try:
            if page:
                error_bytes = await page.screenshot(type="jpeg", quality=60, full_page=True)
                error_screenshot_b64 = await asyncio.to_thread(
                    lambda b: base64.b64encode(b).decode("utf-8"), error_bytes
                )
        except Exception:
            pass

        # Record failure to Neo4j for learning
        await _record_result_to_neo4j(job_id, ats_type_str, success=False)

        await emit_agent_event(session_id, "application_failed", {
            "job_id": job_id,
            "job_title": job.title,
            "company": job.company,
            "error": str(exc),
            "ats_type": ats_type_str,
            "error_screenshot": error_screenshot_b64,
        })

        return ApplicationResult(
            job_id=job_id,
            status=ApplicationStatus.FAILED,
            error_message=str(exc),
            duration_seconds=duration,
        )

    finally:
        if streamer:
            await streamer.stop()
        if ctx_id:
            await manager.close_context(ctx_id)
        await manager.stop()


# ---------------------------------------------------------------------------
# Main agent entry point
# ---------------------------------------------------------------------------

async def run_application_agent(state: JobHunterState) -> dict:
    """Iterate through the application queue and submit applications.

    Uses real Playwright browser automation unless SIMULATE_APPLICATIONS
    is True, in which case it falls back to simulated submissions.

    The circuit breaker pauses the agent after MAX_CONSECUTIVE_FAILURES
    consecutive failures.

    Returns
    -------
    dict
        Keys: applications_submitted, applications_failed,
              consecutive_failures, status, agent_statuses, errors
    """
    errors: List[str] = []
    submitted: List[ApplicationResult] = []
    failed: List[ApplicationResult] = []
    consecutive_failures: int = state.get("consecutive_failures", 0)
    session_id: str = state.get("session_id", "unknown")

    try:
        application_queue: List[str] = state.get("application_queue", [])
        if not application_queue:
            return {
                "applications_submitted": [],
                "applications_failed": [],
                "consecutive_failures": consecutive_failures,
                "status": "applying",
                "agent_statuses": {
                    "application": "completed -- nothing in queue"
                },
                "errors": [],
            }

        logger.info(
            "Application agent starting -- %d jobs in queue",
            len(application_queue),
        )

        total_in_queue = len(application_queue)

        for app_idx, job_id in enumerate(application_queue):
            pct = int((app_idx / total_in_queue) * 100)
            job_obj = _find_job_in_state(job_id, state)
            job_label = f"{job_obj.title} at {job_obj.company}" if job_obj else job_id[:8]
            await emit_agent_event(session_id, "application_progress", {
                "step": f"Applying to {job_label}...",
                "progress": pct,
                "current": app_idx + 1,
                "total": total_in_queue,
            })

            # --- Circuit breaker ---
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.warning(
                    "Circuit breaker tripped after %d consecutive failures -- pausing",
                    consecutive_failures,
                )
                return {
                    "applications_submitted": submitted,
                    "applications_failed": failed,
                    "consecutive_failures": consecutive_failures,
                    "status": "paused",
                    "agent_statuses": {
                        "application": (
                            f"paused -- circuit breaker after "
                            f"{consecutive_failures} consecutive failures"
                        )
                    },
                    "errors": errors,
                }

            try:
                job = _find_job_in_state(job_id, state)
                if job is None:
                    raise ValueError(f"Job {job_id} not found in state -- cannot apply")

                result = await _apply_with_playwright(
                    job_id=job_id,
                    job=job,
                    state=state,
                    session_id=session_id,
                )

                if result.status == ApplicationStatus.SUBMITTED:
                    submitted.append(result)
                    consecutive_failures = 0
                elif result.status == ApplicationStatus.FAILED:
                    failed.append(result)
                    consecutive_failures += 1
                    if result.error_message:
                        errors.append(
                            f"Application failed for {job_id}: {result.error_message}"
                        )
                else:
                    # SKIPPED or other status
                    logger.info("Application %s status: %s", job_id, result.status)
                    consecutive_failures = 0  # don't count skips toward circuit breaker

                done_pct = int(((app_idx + 1) / total_in_queue) * 100)
                await emit_agent_event(session_id, "application_progress", {
                    "step": f"Applied {len(submitted)}/{app_idx + 1} ({len(failed)} failed)",
                    "progress": done_pct,
                    "submitted": len(submitted),
                    "failed": len(failed),
                })

            except Exception as exc:
                error_msg = f"Application failed for job {job_id}: {exc}"
                logger.error(error_msg)
                errors.append(error_msg)

                fail_result = ApplicationResult(
                    job_id=job_id,
                    status=ApplicationStatus.FAILED,
                    error_message=str(exc),
                )
                failed.append(fail_result)
                consecutive_failures += 1

        agent_status = (
            f"completed -- "
            f"{len(submitted)} submitted, {len(failed)} failed"
        )

    except Exception as exc:
        logger.exception("Application agent failed")
        errors.append(f"Application agent error: {exc}")
        agent_status = f"failed -- {exc}"

    return {
        "applications_submitted": submitted,
        "applications_failed": failed,
        "consecutive_failures": consecutive_failures,
        "status": "applying",
        "agent_statuses": {"application": agent_status},
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Alias for graph.py compatibility
# ---------------------------------------------------------------------------
run = run_application_agent
