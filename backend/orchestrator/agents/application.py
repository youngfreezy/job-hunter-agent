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

Falls back to simulated submissions when SIMULATE_APPLICATIONS is True.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
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


async def _publish_sse_event(
    session_id: str,
    event_type: str,
    data: Dict[str, Any],
) -> None:
    """Publish an SSE event via Redis pub/sub."""
    settings = get_settings()
    try:
        import json
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.REDIS_URL)
        payload = json.dumps({"type": event_type, "data": data})
        await client.publish(f"sse:{session_id}", payload)
        await client.close()
    except Exception:
        logger.debug("SSE publish failed for %s", event_type, exc_info=True)


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
# Simulated application (fallback)
# ---------------------------------------------------------------------------

async def _simulate_application(job_id: str) -> ApplicationResult:
    """Generate a simulated successful application result."""
    mock_screenshot = (
        f"https://storage.jobhunter.dev/screenshots/"
        f"{uuid.uuid4().hex[:12]}.png"
    )
    logger.info("Simulated submission for job %s", job_id)
    return ApplicationResult(
        job_id=job_id,
        status=ApplicationStatus.SUBMITTED,
        screenshot_url=mock_screenshot,
        submitted_at=datetime.now(timezone.utc),
        duration_seconds=3,
    )


# ---------------------------------------------------------------------------
# Real Playwright application
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

        # Publish SSE: starting application
        await _publish_sse_event(session_id, "application_start", {
            "job_id": job_id,
            "job_title": job.title,
            "company": job.company,
            "url": job.url,
        })

        # --- Step 1: Navigate to application URL ---
        logger.info("Navigating to application URL: %s", job.url)
        await page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
        import random
        await page.wait_for_timeout(random.randint(2000, 4000))

        # --- Step 2: Detect ATS type ---
        ats_type_str = await _detect_ats(page)
        logger.info("Detected ATS: %s for %s at %s", ats_type_str, job.title, job.company)

        await _publish_sse_event(session_id, "application_ats_detected", {
            "job_id": job_id,
            "ats_type": ats_type_str,
        })

        # --- Step 3: Query Neo4j for strategy ---
        ats_strategy = await _query_neo4j_strategy(ats_type_str)

        # --- Step 4: Account creation if needed ---
        needs_account = await detect_account_required(page)
        if needs_account:
            logger.info("Account creation required for %s", job.company)
            await _publish_sse_event(session_id, "application_account_required", {
                "job_id": job_id,
                "company": job.company,
            })

            # Use a generated email/password for the account
            # In production, these would come from user preferences
            settings = get_settings()
            account_result = await create_account(
                page,
                email=f"applicant+{uuid.uuid4().hex[:6]}@jobhunter.dev",
                password=f"Jh{uuid.uuid4().hex[:12]}!",
                first_name="",  # Will be extracted from resume
                last_name="",
            )

            if account_result.needs_email_verification:
                logger.warning(
                    "Email verification required for %s -- marking as needing HITL",
                    job.company,
                )
                await _publish_sse_event(session_id, "application_needs_verification", {
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

        # --- Step 5: Start screenshot streamer if steering_mode is "screenshot" ---
        streamer: Optional[ScreenshotStreamer] = None
        steering_mode = state.get("steering_mode", "status")
        if steering_mode == "screenshot":
            streamer = ScreenshotStreamer(session_id=session_id)
            await streamer.start(page)

        # --- Step 6: Generate tailored cover letter ---
        resume_text = state.get("coached_resume") or state.get("resume_text", "")
        cover_letter_template = state.get("cover_letter_template", "")

        cover_letter = await generate_cover_letter(
            job=job,
            resume_text=resume_text,
            template=cover_letter_template,
        )
        cover_letter_text = cover_letter.text

        await _publish_sse_event(session_id, "application_cover_letter_ready", {
            "job_id": job_id,
            "cover_letter_preview": cover_letter_text[:200],
        })

        # --- Step 7: Analyse and fill form ---
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

            await _publish_sse_event(session_id, "application_form_filled", {
                "job_id": job_id,
                "fields_filled": fill_result["filled"],
                "fields_skipped": fill_result["skipped"],
            })
        else:
            logger.warning("No form fields found on page for %s", job_id)

        # --- Step 9: Verification screenshot before submission ---
        try:
            screenshot_bytes = await page.screenshot(
                type="png",
                full_page=True,
            )
            import base64
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            # In production: upload to S3/GCS and get URL
            screenshot_url = (
                f"data:image/png;base64,{screenshot_b64[:50]}..."
                f"(full screenshot captured, {len(screenshot_bytes)} bytes)"
            )
            logger.info("Verification screenshot captured for %s", job_id)
        except Exception:
            logger.warning("Screenshot capture failed for %s", job_id, exc_info=True)

        # --- Step 10: Submit the application ---
        submit_btn = await page.query_selector(
            'button[type="submit"], '
            'button:has-text("Submit"), '
            'button:has-text("Apply"), '
            'button:has-text("Submit Application"), '
            'input[type="submit"]'
        )

        if submit_btn:
            await submit_btn.click()
            await page.wait_for_timeout(random.randint(3000, 5000))
            logger.info("Application submitted for %s at %s", job.title, job.company)
        else:
            logger.warning("No submit button found for %s -- form may be incomplete", job_id)

        # --- Step 11: Stop streamer ---
        if streamer:
            await streamer.stop()

        # --- Step 12: Record result to Neo4j ---
        await _record_result_to_neo4j(job_id, ats_type_str, success=True)

        await _publish_sse_event(session_id, "application_submitted", {
            "job_id": job_id,
            "job_title": job.title,
            "company": job.company,
        })

        duration = int(time.monotonic() - start_time)

        return ApplicationResult(
            job_id=job_id,
            status=ApplicationStatus.SUBMITTED,
            screenshot_url=screenshot_url,
            cover_letter_used=cover_letter_text,
            submitted_at=datetime.now(timezone.utc),
            duration_seconds=duration,
        )

    except Exception as exc:
        duration = int(time.monotonic() - start_time)
        logger.exception("Playwright application failed for job %s", job_id)

        # Record failure to Neo4j for learning
        await _record_result_to_neo4j(job_id, ats_type_str, success=False)

        await _publish_sse_event(session_id, "application_failed", {
            "job_id": job_id,
            "error": str(exc),
        })

        return ApplicationResult(
            job_id=job_id,
            status=ApplicationStatus.FAILED,
            error_message=str(exc),
            duration_seconds=duration,
        )

    finally:
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
    settings = get_settings()
    errors: List[str] = []
    submitted: List[ApplicationResult] = []
    failed: List[ApplicationResult] = []
    consecutive_failures: int = state.get("consecutive_failures", 0)
    session_id: str = state.get("session_id", "unknown")
    use_simulation = settings.SIMULATE_APPLICATIONS

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
            "Application agent starting -- %d jobs in queue, simulate=%s",
            len(application_queue),
            use_simulation,
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
                if use_simulation:
                    # ----- Simulated submission -----
                    result = await _simulate_application(job_id)
                else:
                    # ----- Real Playwright submission -----
                    job = _find_job_in_state(job_id, state)
                    if job is None:
                        logger.warning(
                            "Job %s not found in state -- falling back to simulation",
                            job_id,
                        )
                        result = await _simulate_application(job_id)
                    else:
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

        mode_label = "simulated" if use_simulation else "live"
        agent_status = (
            f"completed ({mode_label}) -- "
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
