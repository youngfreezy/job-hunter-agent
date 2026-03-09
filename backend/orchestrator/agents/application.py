# Copyright (c) 2026 V2 Software LLC. All rights reserved.

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
from backend.shared.application_store import (
    check_already_applied,
    check_company_rate_limit,
    record_result as _db_record_result,
)
from backend.shared.billing_store import check_sufficient_credits, debit_wallet
from backend.shared.config import get_settings
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import (
    ApplicationResult,
    ApplicationStatus,
    JobListing,
)

# Credit costs per application outcome
_CREDIT_COST_SUBMITTED = 1.0
_CREDIT_COST_PARTIAL = 0.5


def _charge_for_application(
    user_id: str,
    status: str,
    job_title: str = "",
    job_company: str = "",
    job_id: str = "",
) -> None:
    """Charge the user's wallet based on application outcome.

    - submitted: 1 credit (full charge)
    - failed: 0.5 credits (partial — work was done)
    - skipped: 0 credits (no charge)
    """
    if not user_id or user_id == "unknown":
        return

    if status == "skipped":
        return  # No charge for skips

    amount = _CREDIT_COST_SUBMITTED if status == "submitted" else _CREDIT_COST_PARTIAL
    tx_type = "application_submitted" if status == "submitted" else "application_partial"
    label = f"{job_title} @ {job_company}" if job_title and job_company else job_id
    description = (
        f"Application submitted: {label}" if status == "submitted"
        else f"Partial attempt: {label}"
    )

    try:
        debit_wallet(
            user_id=user_id,
            amount=amount,
            tx_type=tx_type,
            reference_id=job_id,
            description=description,
        )
    except ValueError as e:
        logger.warning("Billing charge failed for user %s: %s", user_id, e)
    except Exception:
        logger.exception("Unexpected billing error for user %s, job %s", user_id, job_id)


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
    "no longer accepting applications",
]

logger = logging.getLogger(__name__)

# Circuit-breaker threshold
MAX_CONSECUTIVE_FAILURES = 3


# ---------------------------------------------------------------------------
# Helpers -- lazy imports to avoid import-time failures when browser
# deps are not installed
# ---------------------------------------------------------------------------

async def _drain_steering_commands(session_id: str) -> List[str]:
    """Return and clear queued steering messages for a session."""
    try:
        import redis.asyncio as aioredis

        settings = get_settings()
        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        key = f"steer:queue:{session_id}"
        messages = await redis_client.lrange(key, 0, -1)
        if messages:
            await redis_client.delete(key)
        await redis_client.close()
        return [m.strip() for m in messages if isinstance(m, str) and m.strip()]
    except Exception:
        logger.debug("Failed to drain steering queue for %s", session_id, exc_info=True)
        return []


def _is_pause_command(message: str) -> bool:
    lower = message.lower()
    return any(token in lower for token in ("pause", "stop applying", "halt"))


def _is_skip_command(message: str) -> bool:
    lower = message.lower()
    has_skip = any(token in lower for token in ("skip", "don't apply", "do not apply"))
    has_target = any(token in lower for token in ("job", "this", "next", "current"))
    return has_skip and has_target


async def _wait_for_intervention_resume(session_id: str, timeout_seconds: int = 600) -> bool:
    """Wait for the UI resume signal set by /resume-intervention."""
    deadline = time.monotonic() + timeout_seconds
    key = f"intervention:resume:{session_id}"

    try:
        import redis.asyncio as aioredis

        settings = get_settings()
        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            while time.monotonic() < deadline:
                value = await redis_client.get(key)
                if value:
                    await redis_client.delete(key)
                    return True
                await asyncio.sleep(2)
            return False
        finally:
            await redis_client.close()
    except Exception:
        logger.debug("Intervention wait failed for %s", session_id, exc_info=True)
        return False


async def _has_captcha(page: Any) -> bool:
    """Detect a VISIBLE captcha challenge blocking the page.

    Only returns True when a captcha is actually blocking interaction (e.g.
    a full-page challenge or a visible iframe). Invisible reCAPTCHA scripts
    embedded in forms (like Greenhouse) do NOT count — they auto-solve.
    """
    try:
        return await page.evaluate(
            """() => {
                // Full-page captcha challenges (Cloudflare, PerimeterX, etc.)
                const fullPageSels = [
                    '#px-captcha', '.cf-challenge-running', '#challenge-running',
                    'div[class*="captcha-container"]',
                ];
                for (const sel of fullPageSels) {
                    const el = document.querySelector(sel);
                    if (el && el.offsetParent !== null) return true;
                }

                // Visible reCAPTCHA / hCaptcha iframes (not just scripts)
                const iframes = document.querySelectorAll(
                    'iframe[src*="recaptcha"][title*="challenge"], iframe[src*="hcaptcha"]'
                );
                for (const iframe of iframes) {
                    if (iframe.offsetParent !== null && iframe.offsetHeight > 50) return true;
                }

                // Check for "I'm not a robot" checkbox that's visible
                const recaptchaWidget = document.querySelector('.g-recaptcha');
                if (recaptchaWidget && recaptchaWidget.offsetParent !== null
                    && recaptchaWidget.offsetHeight > 50) return true;

                return false;
            }"""
        )
    except Exception:
        return False

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
    Handles LinkedIn's externalApply redirect pattern where the real ATS
    URL is URL-encoded inside a query parameter.
    """
    from urllib.parse import urlparse, parse_qs, unquote

    def _extract_ats_url(href: str) -> str | None:
        """Extract the real ATS URL from a link, handling redirects."""
        if not href:
            return None
        href_lower = href.lower()

        # LinkedIn externalApply pattern: ...externalApply/ID?url=ENCODED_ATS_URL
        if "externalapply" in href_lower:
            try:
                parsed = urlparse(href)
                params = parse_qs(parsed.query)
                if "url" in params:
                    decoded = unquote(params["url"][0])
                    if any(d in decoded.lower() for d in _EXTERNAL_ATS_DOMAINS):
                        return decoded
            except Exception:
                pass

        # Direct ATS link
        if any(d in href_lower for d in _EXTERNAL_ATS_DOMAINS):
            return href

        return None

    # Try targeted selectors first
    for sel in _EXTERNAL_APPLY_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el:
                href = await el.get_attribute("href")
                result = _extract_ats_url(href)
                if result:
                    return result
        except Exception:
            continue

    # Scan ALL links on the page (not just apply-text links)
    try:
        links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href]'))
                .map(a => a.href)
        }""")
        for href in (links or []):
            result = _extract_ats_url(href)
            if result:
                return result
    except Exception:
        pass

    # LinkedIn-specific: check for the "Apply" button that triggers external redirect.
    # LinkedIn shows a "Sign up" modal with an embedded external link.
    try:
        # Click the Apply button if it exists (non-Easy-Apply)
        apply_btn = await page.query_selector(
            'button.sign-up-modal__outlet-btn, '
            'button.sign-up-modal__outlet, '
            'button[data-tracking-control-name*="apply"], '
            'button.apply-button'
        )
        if apply_btn:
            btn_text = await apply_btn.inner_text()
            if "easy" not in btn_text.lower():
                await apply_btn.click()
                await asyncio.sleep(1.5)
                # Check if a modal appeared with external link
                modal_links = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a[href]'))
                        .map(a => a.href)
                        .filter(h => h.includes('externalApply') ||
                                    h.includes('greenhouse') ||
                                    h.includes('lever.co') ||
                                    h.includes('myworkdayjobs') ||
                                    h.includes('smartrecruiters'))
                }""")
                for href in (modal_links or []):
                    result = _extract_ats_url(href)
                    if result:
                        return result
                # No external link found — dismiss the modal to restore page state
                try:
                    dismiss = await page.query_selector(
                        'button.modal__dismiss, '
                        'button[aria-label="Dismiss"], '
                        'button[aria-label="Close"]'
                    )
                    if dismiss:
                        await dismiss.click()
                        await asyncio.sleep(0.5)
                except Exception:
                    pass
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


async def _is_dead_page(page: Any) -> bool:
    """Check if the job page is a 404 / expired / removed listing."""
    try:
        text = await page.evaluate("() => document.body.innerText.substring(0, 1000).toLowerCase()")
        for indicator in _NOT_FOUND_INDICATORS:
            if indicator in text:
                return True
        # Also check very short pages (likely errors)
        full_len = await page.evaluate("() => document.body.innerText.length")
        if full_len < 100:
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
    streamer: Any = None

    # Pre-flight: check if user has sufficient credits
    user_id = state.get("user_id", "")
    if user_id and user_id != "unknown":
        if not check_sufficient_credits(user_id):
            logger.info("Insufficient credits for user %s — stopping applications", user_id)
            await emit_agent_event(session_id, "application_progress", {
                "job_id": job_id,
                "step": "Skipped — insufficient credits. Visit Billing to add more.",
            })
            return ApplicationResult(
                job_id=job_id,
                status=ApplicationStatus.SKIPPED,
                error_message="insufficient_credits",
                duration_seconds=int(time.monotonic() - start_time),
            )

    # Pre-flight: skip "Easy Apply" jobs (need board login)
    if getattr(job, "is_easy_apply", False):
        logger.info("Easy Apply job — skipping %s (needs %s login)", job.title, job.board.value)
        await emit_agent_event(session_id, "application_progress", {
            "job_id": job_id,
            "step": f"Skipped — {job.board.value} Easy Apply requires login",
        })
        return ApplicationResult(
            job_id=job_id,
            status=ApplicationStatus.SKIPPED,
            error_message="auth_required",
            duration_seconds=int(time.monotonic() - start_time),
        )

    # Pre-flight: skip jobs already submitted by this user
    prior = check_already_applied(job_id, user_id=user_id)
    if prior:
        applied_at = prior.get("applied_at", "unknown date")
        msg = f"Already applied on {applied_at}"
        logger.info("Duplicate skipped: %s — %s", job.title, msg)
        await emit_agent_event(session_id, "application_progress", {
            "job_id": job_id,
            "step": f"Skipped — {msg}",
        })
        _db_record_result(
            session_id=session_id,
            job_id=job_id,
            status="skipped",
            job_title=job.title,
            job_company=job.company,
            job_url=job.url,
            job_board=job.board.value if hasattr(job.board, "value") else str(job.board),
            job_location=job.location or "",
            error_message=f"duplicate: {msg}",
            user_id=user_id,
        )
        return ApplicationResult(
            job_id=job_id,
            status=ApplicationStatus.SKIPPED,
            error_message=f"duplicate: {msg}",
            duration_seconds=int(time.monotonic() - start_time),
        )

    # Pre-flight: enforce company application rate limit (max 2 per company per 2 weeks)
    company_limit = check_company_rate_limit(job.company, user_id=user_id)
    if company_limit:
        msg = f"Already applied to {company_limit['count']} jobs at {job.company} in the last {company_limit['window_days']} days"
        logger.info("Company rate limit: %s — %s", job.title, msg)
        await emit_agent_event(session_id, "application_progress", {
            "job_id": job_id,
            "step": f"Skipped — {msg}",
        })
        _db_record_result(
            session_id=session_id,
            job_id=job_id,
            status="skipped",
            job_title=job.title,
            job_company=job.company,
            job_url=job.url,
            job_board=job.board.value if hasattr(job.board, "value") else str(job.board),
            job_location=job.location or "",
            error_message=f"company_rate_limit: {msg}",
            user_id=user_id,
        )
        return ApplicationResult(
            job_id=job_id,
            status=ApplicationStatus.SKIPPED,
            error_message=f"company_rate_limit: {msg}",
            duration_seconds=int(time.monotonic() - start_time),
        )

    try:
        from backend.browser.tools.cover_letter import generate_cover_letter

        resume_text = state.get("coached_resume") or state.get("resume_text", "")
        cover_letter_template = state.get("cover_letter_template", "")

        # Compute queue progress for frontend
        _queue = state.get("application_queue", [])
        _done_ids = (
            {r.job_id for r in (state.get("applications_submitted") or [])}
            | {r.job_id for r in (state.get("applications_failed") or [])}
            | set(state.get("applications_skipped") or [])
        )
        _app_idx = len(_done_ids)
        _total_q = len(_queue)
        _pct = int((_app_idx / _total_q) * 100) if _total_q else 0

        await emit_agent_event(session_id, "application_start", {
            "job_id": job_id,
            "job_title": job.title,
            "company": job.company,
            "url": job.url,
            "current": _app_idx + 1,
            "total": _total_q,
            "progress": _pct,
        })

        # --- Step 1: Open tab and navigate (before cover letter to save LLM calls) ---
        page = await context.new_page()
        await apply_stealth(page)

        try:
            # Strip tracking params from LinkedIn URLs (they can cause redirects)
            nav_url = job.url
            if "linkedin.com/jobs/view/" in nav_url:
                from urllib.parse import urlparse, urlunparse
                parsed = urlparse(nav_url)
                nav_url = urlunparse(parsed._replace(query=""))
                logger.info("Cleaned LinkedIn URL: %s", nav_url)
            await page.goto(nav_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(2)  # settle (Bright Data may need longer)
            logger.info("Final page URL after navigation: %s", page.url)

            # If CAPTCHA appears early, pause for manual intervention.
            if await _has_captcha(page):
                await emit_agent_event(session_id, "needs_intervention", {
                    "job_id": job_id,
                    "job_title": job.title,
                    "company": job.company,
                    "reason": "CAPTCHA detected. Solve it in the browser window, then click Resume Agent.",
                })
                resumed = await _wait_for_intervention_resume(session_id, timeout_seconds=600)
                if not resumed:
                    return ApplicationResult(
                        job_id=job_id,
                        status=ApplicationStatus.SKIPPED,
                        error_message="intervention_timeout",
                        duration_seconds=int(time.monotonic() - start_time),
                    )
                await emit_agent_event(session_id, "application_progress", {
                    "job_id": job_id,
                    "step": "Manual intervention received — resuming application...",
                })

            # --- Step 1b: Check if page is dead (404/expired) ---
            if await _is_dead_page(page):
                logger.info("Dead page (404/expired) — skipping %s", job.title)
                await emit_agent_event(session_id, "application_progress", {
                    "job_id": job_id,
                    "step": f"Skipped — job listing expired or removed",
                })
                return ApplicationResult(
                    job_id=job_id,
                    status=ApplicationStatus.SKIPPED,
                    error_message="job_expired",
                    duration_seconds=int(time.monotonic() - start_time),
                )

            # --- Step 1c: Check if redirected to login page ---
            final_url = page.url
            if _is_login_page(final_url):
                logger.info("Login required (%s) for %s", final_url, job.title)
                await emit_agent_event(session_id, "login_required", {
                    "job_id": job_id,
                    "job_title": job.title,
                    "company": job.company,
                    "board": job.board.value,
                    "message": f"Please log in to {job.board.value} in the browser window, then click Resume.",
                })
                try:
                    from backend.orchestrator.agents._login_sync import wait_for_login

                    await wait_for_login(session_id, timeout=300)
                    await emit_agent_event(session_id, "login_complete", {
                        "job_id": job_id,
                        "board": job.board.value,
                    })
                    await page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(1)
                    if _is_login_page(page.url):
                        return ApplicationResult(
                            job_id=job_id,
                            status=ApplicationStatus.SKIPPED,
                            error_message="auth_required",
                            duration_seconds=int(time.monotonic() - start_time),
                        )
                except Exception:
                    return ApplicationResult(
                        job_id=job_id,
                        status=ApplicationStatus.SKIPPED,
                        error_message="auth_timeout",
                        duration_seconds=int(time.monotonic() - start_time),
                    )

            # --- Step 1c: Check for external apply link ---
            # Many board pages (LinkedIn, ZipRecruiter, etc.) have an
            # "Apply on company site" link that goes to an external ATS
            # (Greenhouse, Lever, Workday).  Follow it if found.
            # Skip if already on an ATS domain (avoid leaving a form page).
            current_lower = page.url.lower()
            already_on_ats = any(d in current_lower for d in _EXTERNAL_ATS_DOMAINS)
            external_url = None if already_on_ats else await _find_external_apply_link(page)
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

            # --- Step 2: Generate cover letter (only if enabled in config) ---
            session_config = state.get("session_config")
            should_generate_cl = True  # default
            if session_config:
                _cfg = session_config if isinstance(session_config, dict) else (session_config.model_dump() if hasattr(session_config, "model_dump") else {})
                should_generate_cl = _cfg.get("generate_cover_letters", True)

            cover_letter_text = ""
            if should_generate_cl:
                await emit_agent_event(session_id, "application_progress", {
                    "job_id": job_id,
                    "step": f"Generating cover letter for {job.title} at {job.company}...",
                    "current": _app_idx + 1,
                    "total": _total_q,
                    "progress": _pct,
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
                "step": f"Filling application form ({applier.PLATFORM}) for {job.title}...",
                "current": _app_idx + 1,
                "total": _total_q,
                "progress": _pct,
            })

            # --- Step 6: Run application ---
            result = await applier.run(
                job=job,
                user_profile=user_profile,
                resume_text=resume_text,
                cover_letter=cover_letter_text,
                resume_file_path=resume_file,
            )

            # --- Step 6b: Handle external redirect from LinkedIn applier ---
            # When LinkedIn applier finds an external ATS link instead of
            # Easy Apply, it returns a special error_message starting with
            # "external_redirect:" followed by the URL.
            if (
                result.status == ApplicationStatus.SKIPPED
                and result.error_message
                and result.error_message.startswith("external_redirect:")
            ):
                external_url = result.error_message.split("external_redirect:", 1)[1]
                logger.info(
                    "Following external redirect for %s: %s",
                    job.title, external_url,
                )
                await emit_agent_event(session_id, "application_progress", {
                    "job_id": job_id,
                    "step": f"Following external apply link...",
                })
                await page.goto(external_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(1)

                # Re-detect ATS and use appropriate applier
                ats_type = await detect_ats_type(page)
                logger.info("External ATS detected: %s for %s", ats_type.value, page.url)
                applier = get_applier(job.board.value, ats_type, page, session_id)
                logger.info("Using %s applier (external) for %s", applier.PLATFORM, job.title)
                await emit_agent_event(session_id, "application_progress", {
                    "job_id": job_id,
                    "step": f"Filling application form ({applier.PLATFORM}) for {job.title}...",
                    "current": _app_idx + 1,
                    "total": _total_q,
                    "progress": _pct,
                })
                result = await applier.run(
                    job=job,
                    user_profile=user_profile,
                    resume_text=resume_text,
                    cover_letter=cover_letter_text,
                    resume_file_path=resume_file,
                )

            # --- Step 7: Fallback to browser-use if SKIPPED ---
            # Only fall back for non-auth skips (e.g., complex form).
            # Auth-related skips are hopeless — browser-use can't log in either.
            skip_reason = (result.error_message or "").lower()
            auth_skip = any(kw in skip_reason for kw in [
                "auth", "login", "sign in", "easy apply",
            ])
            if result.status == ApplicationStatus.SKIPPED and not auth_skip:
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

        # Persist to DB immediately (survives restarts)
        # Always store the cover letter and tailored resume regardless of success/failure
        _tailored = state.get("tailored_resumes", {}).get(job_id)
        _tailored_text = None
        if _tailored:
            _tailored_text = _tailored.tailored_text if hasattr(_tailored, "tailored_text") else _tailored.get("tailored_text")
        _db_record_result(
            session_id=session_id,
            job_id=job_id,
            status=result.status.value,
            job_title=job.title,
            job_company=job.company,
            job_url=job.url,
            job_board=job.board.value if hasattr(job.board, "value") else str(job.board),
            job_location=job.location or "",
            error_message=result.error_message,
            cover_letter=result.cover_letter_used or cover_letter_text,
            tailored_resume_text=_tailored_text,
            duration_seconds=result.duration_seconds,
            screenshot_path=result.screenshot_url,
            user_id=user_id,
        )

        # Charge the user based on outcome
        user_id = state.get("user_id", "")
        _charge_for_application(
            user_id=user_id,
            status=result.status.value,
            job_title=job.title,
            job_company=job.company,
            job_id=job_id,
        )

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

        _db_record_result(
            session_id=session_id,
            job_id=job_id,
            status="failed",
            job_title=job.title,
            job_company=job.company,
            job_url=job.url,
            job_board=job.board.value if hasattr(job.board, "value") else str(job.board),
            job_location=job.location or "",
            error_message=str(exc),
            duration_seconds=duration,
            user_id=user_id,
        )

        # Charge partial credit for failed attempt (work was done)
        user_id = state.get("user_id", "")
        _charge_for_application(
            user_id=user_id,
            status="failed",
            job_title=job.title,
            job_company=job.company,
            job_id=job_id,
        )

        # Enqueue to dead letter queue for review/retry
        from backend.shared.dead_letter_queue import enqueue_failed_application
        enqueue_failed_application(
            session_id=session_id,
            user_id=user_id,
            job_id=job_id,
            job_title=job.title,
            job_company=job.company,
            job_url=job.url,
            job_board=job.board.value if hasattr(job.board, "value") else str(job.board),
            error_message=str(exc)[:500],
            error_type=type(exc).__name__,
        )

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
    """Process the next pending application in the queue.

    Uses BrowserManager (Patchright) with platform-specific Playwright
    appliers. Falls back to browser-use for unknown forms. The graph loops
    this node between jobs so the workflow supervisor can authoritatively
    steer the run after every application attempt.

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
    user_id: str = state.get("user_id", "")

    manager: Optional[BrowserManager] = None

    try:
        application_queue: List[str] = state.get("application_queue", [])
        if not application_queue:
            return {
                "applications_submitted": [],
                "applications_failed": [],
                "applications_skipped": [],
                "consecutive_failures": consecutive_failures,
                "status": "applying",
                "agent_statuses": {
                    "application": "completed -- nothing in queue"
                },
                "errors": [],
                "skip_next_job_requested": False,
            }

        submitted_ids = {r.job_id for r in (state.get("applications_submitted") or [])}
        failed_ids = {r.job_id for r in (state.get("applications_failed") or [])}
        skipped_ids = set(state.get("applications_skipped") or [])
        done_ids = submitted_ids | failed_ids | skipped_ids
        remaining = [job_id for job_id in application_queue if job_id not in done_ids]
        if not remaining:
            return {
                "applications_submitted": [],
                "applications_failed": [],
                "applications_skipped": [],
                "consecutive_failures": consecutive_failures,
                "status": "applying",
                "agent_statuses": {
                    "application": "completed -- queue exhausted"
                },
                "errors": [],
                "skip_next_job_requested": False,
            }

        logger.info(
            "Application agent starting -- %d jobs pending of %d total",
            len(remaining),
            len(application_queue),
        )
        total_in_queue = len(application_queue)
        processed_count = len(done_ids)
        app_idx = processed_count
        job_id = remaining[0]
        pct = int((app_idx / total_in_queue) * 100) if total_in_queue else 0
        job_obj = _find_job_in_state(job_id, state)
        job_label = f"{job_obj.title} at {job_obj.company}" if job_obj else job_id[:8]

        if state.get("skip_next_job_requested"):
            skipped_result = ApplicationResult(
                job_id=job_id,
                status=ApplicationStatus.SKIPPED,
                error_message="skipped_by_workflow_supervisor",
                duration_seconds=0,
            )
            skipped.append(skipped_result)
            if job_obj is not None:
                _db_record_result(
                    session_id=session_id,
                    job_id=job_id,
                    status="skipped",
                    job_title=job_obj.title,
                    job_company=job_obj.company,
                    job_url=job_obj.url,
                    job_board=job_obj.board.value if hasattr(job_obj.board, "value") else str(job_obj.board),
                    job_location=job_obj.location or "",
                    error_message="skipped_by_workflow_supervisor",
                    user_id=user_id,
                )
            await emit_agent_event(session_id, "application_progress", {
                "step": f"Skipped {job_label} (workflow steering)",
                "progress": pct,
                "current": app_idx + 1,
                "total": total_in_queue,
            })
            return {
                "applications_submitted": [],
                "applications_failed": [],
                "applications_skipped": [job_id],
                "consecutive_failures": 0,
                "status": "applying",
                "agent_statuses": {"application": f"skipped -- {job_label}"},
                "errors": [],
                "skip_next_job_requested": False,
            }

        # --- Circuit breaker ---
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            logger.warning(
                "Circuit breaker tripped after %d consecutive failures -- pausing",
                consecutive_failures,
            )
            return {
                "applications_submitted": [],
                "applications_failed": [],
                "applications_skipped": [],
                "consecutive_failures": consecutive_failures,
                "status": "paused",
                "agent_statuses": {
                    "application": (
                        f"paused -- circuit breaker after "
                        f"{consecutive_failures} consecutive failures"
                    )
                },
                "errors": errors,
                "skip_next_job_requested": False,
            }

        prev_submitted = len(state.get("applications_submitted") or [])
        prev_failed = len(state.get("applications_failed") or [])
        prev_skipped = len(state.get("applications_skipped") or [])
        await emit_agent_event(session_id, "application_progress", {
            "step": f"Applying to {job_label} ({app_idx + 1} of {total_in_queue})...",
            "progress": pct,
            "current": app_idx + 1,
            "total": total_in_queue,
            "submitted": prev_submitted,
            "failed": prev_failed,
            "skipped": prev_skipped,
        })

        settings = get_settings()
        job = _find_job_in_state(job_id, state)
        if job is None:
            raise ValueError(f"Job {job_id} not found in state -- cannot apply")

        manager = BrowserManager()
        await manager.start_for_task(
            board=job.board,
            purpose="apply",
            headless=settings.BROWSER_HEADLESS,
        )

        _, context = await manager.new_context()

        try:
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
                    errors.append(f"Application failed for {job_id}: {result.error_message}")
            else:
                skipped.append(result)
                consecutive_failures = 0

            done_pct = int(((app_idx + 1) / total_in_queue) * 100)
            status_label = (
                f"{len(submitted)} submitted, {len(failed)} failed"
                f"{', 1 skipped' if skipped else ''} — {app_idx + 1} of {total_in_queue} processed"
            )
            await emit_agent_event(session_id, "application_progress", {
                "step": status_label,
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

            if job_obj is not None:
                _db_record_result(
                    session_id=session_id,
                    job_id=job_id,
                    status="failed",
                    job_title=job_obj.title,
                    job_company=job_obj.company,
                    job_url=job_obj.url,
                    job_board=job_obj.board.value if hasattr(job_obj.board, "value") else str(job_obj.board),
                    job_location=job_obj.location or "",
                    error_message=str(exc),
                    user_id=user_id,
                )

        agent_status = f"processed -- {job_label}"

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
        try:
            from backend.orchestrator.agents._login_sync import cleanup as _cleanup_login

            _cleanup_login(session_id)
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
        "skip_next_job_requested": False,
    }


# ---------------------------------------------------------------------------
# Alias for graph.py compatibility
# ---------------------------------------------------------------------------
run = run_application_agent
