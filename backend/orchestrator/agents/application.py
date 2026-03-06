"""Application Agent -- submits job applications via direct Playwright + LLM form analysis.

Uses platform-specific Playwright appliers for known boards/ATS platforms,
with browser-use as a fallback for truly unknown forms.

For each job in the queue:
1. Generate a tailored cover letter
2. Extract user profile from resume
3. Detect ATS type → dispatch to appropriate applier
4. Fill forms via LLM analysis (1-3 calls instead of 30)
5. Record the result to Neo4j
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from backend.browser.manager import BrowserManager, apply_stealth
from backend.browser.tools.ats_detector import detect_ats_type
from backend.browser.tools.appliers import get_applier
from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.config import get_settings
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import (
    ApplicationResult,
    ApplicationStatus,
    JobListing,
)

# Login page indicators — if the final URL contains any of these after
# navigation, the page requires authentication and should be skipped.
_LOGIN_INDICATORS = [
    "login", "signin", "sign-in", "sign_in", "auth",
    "accounts.google.com", "login.microsoftonline.com",
    "sso.", "oauth", "authenticate",
]

# Text on page that indicates an auth wall / signup gate is blocking access.
# These appear in the page body when the board shows a login overlay instead
# of redirecting to a /login URL.
_AUTH_WALL_INDICATORS = [
    "sign in to apply",
    "log in to apply",
    "create an account",
    "sign up to apply",
    "join now to apply",
    "sign in to continue",
    "please sign in",
    "please log in",
    "email address to apply",
    "enter your email",
]

# Page-not-found indicators — skip expired/removed job pages fast.
_NOT_FOUND_INDICATORS = [
    "404", "page not found", "this page could not be found",
    "job has been removed", "no longer available",
    "this job has expired", "position has been filled",
    "job posting has been removed", "this listing has expired",
]

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


def _is_login_page(url: str) -> bool:
    """Return True if the URL looks like a login/authentication page."""
    url_lower = url.lower()
    return any(ind in url_lower for ind in _LOGIN_INDICATORS)


# Domains that host external ATS application forms (public, no auth needed)
_EXTERNAL_ATS_DOMAINS = [
    "greenhouse.io", "boards.greenhouse.io",
    "lever.co", "jobs.lever.co",
    "myworkdayjobs.com", "wd1.myworkdayjobs.com", "wd3.myworkdayjobs.com", "wd5.myworkdayjobs.com",
    "smartrecruiters.com", "jobs.smartrecruiters.com",
    "icims.com",
    "jobvite.com",
    "ashbyhq.com",
    "bamboohr.com",
    "breezy.hr",
    "recruitee.com",
    "workable.com",
    "jazz.co",
    "applytojob.com",
]

# Selectors for "Apply on company website" / external apply links on board pages
_EXTERNAL_APPLY_SELECTORS = [
    # LinkedIn
    'a.apply-button[href*="greenhouse"]',
    'a.apply-button[href*="lever"]',
    'a.apply-button[href*="workday"]',
    'a[href*="greenhouse.io"]',
    'a[href*="lever.co"]',
    'a[href*="myworkdayjobs.com"]',
    'a[href*="smartrecruiters.com"]',
    'a[href*="icims.com"]',
    'a[href*="jobvite.com"]',
    'a[href*="ashbyhq.com"]',
    # Generic "Apply on company site" patterns
    'a:has-text("Apply on company")',
    'a:has-text("Apply on employer")',
    'a:has-text("apply on company")',
    'a:has-text("External Apply")',
    'a:has-text("Apply Now")',
    # ZipRecruiter external link
    'a.job_apply_url',
    'a[data-testid="apply-link"]',
]


async def _find_external_apply_link(page: Any) -> str | None:
    """Look for an external apply link on a board job page.

    Returns the external URL if found, None otherwise.
    """
    for sel in _EXTERNAL_APPLY_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el:
                href = await el.get_attribute("href")
                if href and any(domain in href.lower() for domain in _EXTERNAL_ATS_DOMAINS):
                    return href
        except Exception:
            continue

    # Fallback: scan all links on the page for external ATS domains
    try:
        links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href]'))
                .map(a => ({ href: a.href, text: a.innerText.trim().toLowerCase() }))
                .filter(l => l.text.includes('apply') || l.text.includes('submit'))
        }""")
        for link in (links or []):
            href = link.get("href", "")
            if any(domain in href.lower() for domain in _EXTERNAL_ATS_DOMAINS):
                return href
    except Exception:
        pass

    return None


async def _has_auth_wall(page: Any) -> bool:
    """Check if the current page shows an auth wall/signup gate.

    Some boards (ZipRecruiter, LinkedIn) don't redirect to a /login URL
    but show an overlay or gate that blocks the apply flow.
    """
    try:
        text = await page.evaluate("() => document.body.innerText.toLowerCase()")
        for indicator in _AUTH_WALL_INDICATORS:
            if indicator in text:
                return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Direct Playwright application (with browser-use fallback)
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


async def _apply_to_job(
    job_id: str,
    job: JobListing,
    state: JobHunterState,
    session_id: str,
    context: Any = None,
) -> ApplicationResult:
    """Apply to a single job using direct Playwright + LLM form analysis.

    Dispatch chain:
    1. Open new tab in shared headless context
    2. Navigate to job URL
    3. Check for login redirect → skip if auth required
    4. Detect ATS type from URL/page
    5. Select board/ATS-specific applier
    6. Run direct Playwright application
    7. If applier returns SKIPPED → fallback to browser-use
    """
    start_time = time.monotonic()
    detected_ats = "unknown"

    try:
        from backend.browser.tools.cover_letter import generate_cover_letter

        resume_text = state.get("coached_resume") or state.get("resume_text", "")
        cover_letter_template = state.get("cover_letter_template", "")

        await emit_agent_event(session_id, "application_start", {
            "job_id": job_id,
            "job_title": job.title,
            "company": job.company,
            "url": job.url,
        })

        # --- Step 1: Open tab and navigate (before cover letter to save LLM calls) ---
        page = await context.new_page()
        await apply_stealth(page)

        try:
            await page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(1)  # settle

            # --- Step 1b: Check if redirected to login page ---
            final_url = page.url
            if _is_login_page(final_url):
                logger.info("Login page detected (%s) — skipping %s", final_url, job.title)
                await emit_agent_event(session_id, "application_progress", {
                    "job_id": job_id,
                    "step": f"Skipped — requires authentication ({job.board.value})",
                })
                return ApplicationResult(
                    job_id=job_id,
                    status=ApplicationStatus.SKIPPED,
                    error_message="auth_required",
                    duration_seconds=int(time.monotonic() - start_time),
                )

            # --- Step 1c: Check for external apply link ---
            # Many board pages (LinkedIn, ZipRecruiter, etc.) have an
            # "Apply on company site" link that goes to an external ATS
            # (Greenhouse, Lever, Workday).  Follow it if found.
            external_url = await _find_external_apply_link(page)
            if external_url:
                logger.info(
                    "Found external apply link: %s → %s",
                    job.url, external_url,
                )
                await emit_agent_event(session_id, "application_progress", {
                    "job_id": job_id,
                    "step": f"Following external apply link...",
                })
                await page.goto(external_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(1)

                # Re-check for login redirect on the new page
                final_url = page.url
                if _is_login_page(final_url):
                    logger.info("External link led to login page — skipping %s", job.title)
                    await emit_agent_event(session_id, "application_progress", {
                        "job_id": job_id,
                        "step": f"Skipped — external page requires authentication",
                    })
                    return ApplicationResult(
                        job_id=job_id,
                        status=ApplicationStatus.SKIPPED,
                        error_message="auth_required",
                        duration_seconds=int(time.monotonic() - start_time),
                    )

            # --- Step 1d: Check for in-page auth wall (signup gate) ---
            if await _has_auth_wall(page):
                logger.info("Auth wall detected on page — skipping %s", job.title)
                await emit_agent_event(session_id, "application_progress", {
                    "job_id": job_id,
                    "step": f"Skipped — page requires login to apply ({job.board.value})",
                })
                return ApplicationResult(
                    job_id=job_id,
                    status=ApplicationStatus.SKIPPED,
                    error_message="auth_required",
                    duration_seconds=int(time.monotonic() - start_time),
                )

            # --- Step 2: Generate cover letter (only if we'll actually apply) ---
            await emit_agent_event(session_id, "application_progress", {
                "job_id": job_id,
                "step": "Generating tailored cover letter...",
            })
            cover_letter = await generate_cover_letter(
                job=job,
                resume_text=resume_text,
                template=cover_letter_template,
            )
            cover_letter_text = cover_letter.text

            # --- Step 3: Extract user profile ---
            user_profile = await _extract_user_profile(state)
            resume_file = state.get("resume_file_path")

            # --- Step 4: Detect ATS type ---
            ats_type = await detect_ats_type(page)
            detected_ats = ats_type.value
            logger.info("ATS detected: %s for %s", detected_ats, page.url)

            # --- Step 5: Get appropriate applier ---
            applier = get_applier(job.board.value, ats_type, page, session_id)
            logger.info("Using %s applier for %s", applier.PLATFORM, job.title)

            await emit_agent_event(session_id, "application_progress", {
                "job_id": job_id,
                "step": f"Applying via {applier.PLATFORM} applier...",
            })

            # --- Step 6: Run application ---
            result = await applier.apply(
                job=job,
                user_profile=user_profile,
                resume_text=resume_text,
                cover_letter=cover_letter_text,
                resume_file_path=resume_file,
            )

            # --- Step 7: Fallback to browser-use if SKIPPED ---
            if result.status == ApplicationStatus.SKIPPED:
                logger.warning(
                    "Applier returned SKIPPED for %s — falling back to browser-use",
                    job.title,
                )
                await emit_agent_event(session_id, "application_progress", {
                    "job_id": job_id,
                    "step": "Using AI agent (fallback) for complex form...",
                })
                await page.close()
                page = None

                from backend.browser.tools.browser_use_applier import apply_with_browser_use
                result = await apply_with_browser_use(
                    job=job,
                    resume_text=resume_text,
                    cover_letter=cover_letter_text,
                    user_profile=user_profile,
                    session_id=session_id,
                    resume_file_path=resume_file,
                )

        finally:
            if page and not page.is_closed():
                await page.close()

        # --- Step 8: Record to Neo4j ---
        success = result.status == ApplicationStatus.SUBMITTED
        await _record_result_to_neo4j(job_id, detected_ats, success=success)

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

        await _record_result_to_neo4j(job_id, detected_ats, success=False)

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

    Uses BrowserManager (Patchright) with platform-specific Playwright
    appliers. Falls back to browser-use for unknown forms.

    Returns
    -------
    dict
        Keys: applications_submitted, applications_failed,
              consecutive_failures, status, agent_statuses, errors
    """
    errors: List[str] = []
    submitted: List[ApplicationResult] = []
    failed: List[ApplicationResult] = []
    skipped: List[ApplicationResult] = []
    consecutive_failures: int = state.get("consecutive_failures", 0)
    session_id: str = state.get("session_id", "unknown")

    manager: Optional[BrowserManager] = None

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

        # Start BrowserManager (Patchright, fully headless — no auth)
        manager = BrowserManager()
        await manager.start(headless=True)

        # Create a shared context
        ctx_id, context = await manager.new_context()

        total_in_queue = len(application_queue)

        for app_idx, job_id in enumerate(application_queue):
            # Rate-limit cooldown between jobs (skip for first job)
            if app_idx > 0:
                cooldown = 5  # seconds -- direct Playwright is fast, minimal delay needed
                await emit_agent_event(session_id, "application_progress", {
                    "step": f"Waiting {cooldown}s before next application...",
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
                    "applications_skipped": [r.job_id for r in skipped],
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

                result = await _apply_to_job(
                    job_id=job_id,
                    job=job,
                    state=state,
                    session_id=session_id,
                    context=context,
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
                    skipped.append(result)
                    logger.info("Application %s status: %s", job_id, result.status)
                    consecutive_failures = 0

                done_pct = int(((app_idx + 1) / total_in_queue) * 100)
                skipped_msg = f", {len(skipped)} skipped" if skipped else ""
                await emit_agent_event(session_id, "application_progress", {
                    "step": f"{len(submitted)} submitted, {len(failed)} failed{skipped_msg} — {app_idx + 1} of {total_in_queue} processed",
                    "progress": done_pct,
                    "submitted": len(submitted),
                    "failed": len(failed),
                    "skipped": len(skipped),
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

    finally:
        if manager:
            try:
                await manager.stop()
            except Exception:
                pass

    return {
        "applications_submitted": submitted,
        "applications_failed": failed,
        "applications_skipped": [r.job_id for r in skipped],
        "consecutive_failures": consecutive_failures,
        "status": "applying",
        "agent_statuses": {"application": agent_status},
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Alias for graph.py compatibility
# ---------------------------------------------------------------------------
run = run_application_agent
