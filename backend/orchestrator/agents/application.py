"""Application Agent -- submits job applications via browser-use AI agent.

Uses browser-use (LLM-driven browser automation) to dynamically navigate
job application pages, fill forms, and submit — no hardcoded CSS selectors.

For each job in the queue:
1. Generate a tailored cover letter
2. Extract user profile from resume
3. Launch browser-use agent to apply (handles any ATS, LinkedIn Easy Apply, etc.)
4. Record the result to Neo4j
"""

from __future__ import annotations

import asyncio
import logging
import time
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
# browser-use application
# ---------------------------------------------------------------------------

async def _extract_user_profile(state: JobHunterState) -> Dict[str, str]:
    """Extract user profile info (name, email, phone, location) from resume text."""
    import re as _re

    resume_text = state.get("coached_resume") or state.get("resume_text", "")
    profile: Dict[str, str] = {}

    # Extract email
    email_match = _re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', resume_text)
    if email_match:
        profile["email"] = email_match.group(0)

    # Extract phone
    phone_match = _re.search(r'[\+]?[\d\s\-\(\)]{10,}', resume_text)
    if phone_match:
        profile["phone"] = phone_match.group(0).strip()

    # Extract name from first line
    first_line = resume_text.strip().split("\n")[0].strip()
    if first_line and not _re.search(r'[@\d]', first_line):
        profile["name"] = first_line

    # Location: look for common patterns
    loc_match = _re.search(
        r'(?:^|\n)\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s*[A-Z]{2})\s*(?:\n|$)',
        resume_text,
    )
    if loc_match:
        profile["location"] = loc_match.group(1)

    return profile


async def _apply_with_playwright(
    job_id: str,
    job: JobListing,
    state: JobHunterState,
    session_id: str,
) -> ApplicationResult:
    """Submit a job application using browser-use AI agent.

    browser-use dynamically analyses each page and determines what to
    click, fill, and submit — no hardcoded CSS selectors needed.

    Steps:
    1. Generate tailored cover letter
    2. Extract user profile from resume
    3. Run browser-use agent to navigate, fill, and submit the application
    4. Record result to Neo4j
    """
    start_time = time.monotonic()

    try:
        # --- Step 1: Generate tailored cover letter ---
        from backend.browser.tools.cover_letter import generate_cover_letter

        resume_text = state.get("coached_resume") or state.get("resume_text", "")
        cover_letter_template = state.get("cover_letter_template", "")

        await emit_agent_event(session_id, "application_start", {
            "job_id": job_id,
            "job_title": job.title,
            "company": job.company,
            "url": job.url,
        })

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

        # --- Step 2: Extract user profile ---
        user_profile = await _extract_user_profile(state)
        resume_file = state.get("resume_file_path")

        # --- Step 3: Run browser-use agent ---
        from backend.browser.tools.browser_use_applier import apply_with_browser_use

        result = await apply_with_browser_use(
            job=job,
            resume_text=resume_text,
            cover_letter=cover_letter_text,
            user_profile=user_profile,
            session_id=session_id,
            resume_file_path=resume_file,
        )

        # --- Step 4: Record to Neo4j ---
        success = result.status == ApplicationStatus.SUBMITTED
        await _record_result_to_neo4j(job_id, "unknown", success=success)

        # Emit final SSE event
        if success:
            await emit_agent_event(session_id, "application_submitted", {
                "job_id": job_id,
                "job_title": job.title,
                "company": job.company,
            })
        else:
            await emit_agent_event(session_id, "application_failed", {
                "job_id": job_id,
                "job_title": job.title,
                "company": job.company,
                "error": result.error_message or "Application did not complete",
            })

        return result

    except Exception as exc:
        duration = int(time.monotonic() - start_time)
        logger.exception("Application failed for job %s", job_id)

        await _record_result_to_neo4j(job_id, "unknown", success=False)

        await emit_agent_event(session_id, "application_failed", {
            "job_id": job_id,
            "job_title": job.title,
            "company": job.company,
            "error": str(exc),
        })

        return ApplicationResult(
            job_id=job_id,
            status=ApplicationStatus.FAILED,
            error_message=str(exc),
            duration_seconds=duration,
        )


# ---------------------------------------------------------------------------
# Main agent entry point
# ---------------------------------------------------------------------------

async def run_application_agent(state: JobHunterState) -> dict:
    """Iterate through the application queue and submit applications.

    Uses browser-use (LLM-driven browser automation) for each application.
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
            # Rate-limit cooldown between jobs (skip for first job)
            if app_idx > 0:
                cooldown = 60  # seconds — must exceed the 1-min rate-limit window
                await emit_agent_event(session_id, "application_progress", {
                    "step": f"Waiting {cooldown}s before the next application to avoid rate limits...",
                    "progress": int((app_idx / total_in_queue) * 100),
                    "current": app_idx + 1,
                    "total": total_in_queue,
                })
                await asyncio.sleep(cooldown)

            pct = int((app_idx / total_in_queue) * 100)
            job_obj = _find_job_in_state(job_id, state)
            job_label = f"{job_obj.title} at {job_obj.company}" if job_obj else job_id[:8]
            await emit_agent_event(session_id, "application_progress", {
                "step": f"Applying to {job_label} ({app_idx + 1} of {total_in_queue})...",
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
                    "step": f"{len(submitted)} submitted, {len(failed)} failed — {app_idx + 1} of {total_in_queue} processed",
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
