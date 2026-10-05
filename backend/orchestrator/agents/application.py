# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Execute application decisions using the configured browser and persistence.

Browserbase and Stagehand drive the default Indeed flow. Experimental direct API
submission stays disabled by default. Pure queue, routing and outcome decisions
live in application_policy; this module owns browser/model/storage effects.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from backend.browser.manager import BrowserManager, apply_stealth
from backend.orchestrator.application_policy import (
    MAX_CONSECUTIVE_FAILURES,
    ApplicationCandidate,
    ApplicationPolicy,
    ApplicationSupervisorResult,
    OutcomeKind,
    SupervisorDecision,
    classify_outcome,
    completed_job_ids,
    fallback_supervisor_decision as _hardcoded_fallback,
    infer_error_category as _infer_error_category,
    requires_explicit_pause,
    select_company_batch,
    select_explicit_pause,
)
from backend.orchestrator.pipeline.state import JobHunterState
from backend.shared.application_store import (
    DuplicateCheckUnavailable,
    check_already_applied,
    check_company_rate_limit,
    clear_pending,
    record_result as _db_record_result,
)
from backend.shared.billing_store import check_sufficient_credits, debit_wallet
from backend.shared.config import get_settings
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import (
    ApplicationErrorCategory,
    ApplicationResult,
    ApplicationStatus,
    ATSType,
    JobListing,
    JobBoard,
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

def _application_policy() -> ApplicationPolicy:
    """Snapshot runtime configuration at the I/O boundary."""
    settings = get_settings()
    return ApplicationPolicy(
        api_enabled=settings.API_APPLY_ENABLED,
        indeed_only=settings.INDEED_ONLY,
        easy_apply_only=settings.INDEED_EASY_APPLY_ONLY,
        browser_concurrency=settings.SKYVERN_CONCURRENCY,
    )


_SUPERVISOR_SYSTEM = """\
You are a supervisor for a job application automation system. After each failed \
application attempt, you decide what the system should do next.

You will receive:
- The error details from the failed attempt
- A summary of recent failures in this session
- How many jobs remain in the queue
- Whether this is a Quick Apply session (user explicitly chose these URLs)

## Decisions

- "continue": The failure is job-specific or site-specific (expired listing, auth wall, \
captcha on one site, duplicate). Move to the next job.
- "pause": Multiple consecutive failures suggest a systemic problem (e.g., resume upload \
broken across sites, Skyvern navigation failing repeatedly, form fill errors on \
different ATS platforms). Stop and let the user review.
- "abort": An unrecoverable condition (credits exhausted, all remaining jobs share the \
same systemic blocker). Proceed directly to summary.

## Key rules

1. Site-specific blockers (auth walls, captchas, expired listings, duplicates) should \
ALWAYS be "continue" — these say nothing about whether the next job will work.

2. A failure is "systemic" if it indicates the automation itself is broken — form fill \
errors, submit button not found, timeout on multiple different sites, navigation failures.

3. Quick Apply: The user hand-picked these URLs. Be aggressive about continuing. Only \
pause after 5+ consecutive systemic failures. Never abort unless credits are exhausted.

4. Standard sessions: Pause after 3 consecutive systemic failures.

5. Set is_systemic=true only for failures that indicate the automation is broken, not \
for site-specific issues the automation can't control.\
"""


def _build_supervisor_context(
    result: ApplicationResult,
    failed_history: list,
    remaining_count: int,
    is_quick_apply: bool,
) -> str:
    """Build compact JSON context for the supervisor LLM."""
    import json as _json

    effective_cat = result.error_category or _infer_error_category(result.error_message)

    recent_failures = []
    for f in failed_history[-5:]:
        cat = f.error_category or _infer_error_category(f.error_message)
        recent_failures.append({
            "error": (f.error_message or "unknown")[:100],
            "category": cat.value if cat else "unknown",
        })

    return _json.dumps({
        "current_failure": {
            "error_message": (result.error_message or "")[:200],
            "error_category": effective_cat.value if effective_cat else None,
            "failure_step": result.failure_step,
        },
        "session_history": {
            "total_failures": len(failed_history),
            "recent_failures": recent_failures,
        },
        "remaining_jobs": remaining_count,
        "is_quick_apply": is_quick_apply,
    }, indent=2)


async def _call_application_supervisor(
    result: ApplicationResult,
    failed_history: list,
    remaining_count: int,
    is_quick_apply: bool,
    session_id: str,
) -> ApplicationSupervisorResult:
    """Ask the LLM supervisor what to do after a failure.

    Falls back to hardcoded logic if the LLM call fails.
    """
    if result.failure_step == 'duplicate_check':
        return ApplicationSupervisorResult(
            decision=SupervisorDecision.PAUSE,
            reasoning="Application history is unavailable. Restore storage before resuming; no submission was attempted.",
            is_systemic=True,
        )
    if result.failure_step == 'model_budget':
        from backend.browser.stagehand_budget import CEILING_STOP, BUDGET_STOP
        return ApplicationSupervisorResult(
            decision=SupervisorDecision.PAUSE,
            reasoning=(result.error_message if result.error_message in (CEILING_STOP, BUDGET_STOP)
                       else BUDGET_STOP),
            is_systemic=True,
        )
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from backend.shared.llm import build_llm, invoke_with_retry, HAIKU_MODEL

        llm = build_llm(model=HAIKU_MODEL, max_tokens=256, temperature=0.0)
        structured_llm = llm.with_structured_output(ApplicationSupervisorResult)

        context = _build_supervisor_context(
            result, failed_history, remaining_count, is_quick_apply,
        )

        messages = [
            SystemMessage(content=_SUPERVISOR_SYSTEM),
            HumanMessage(content=context),
        ]

        decision = await invoke_with_retry(structured_llm, messages, max_retries=1)

        logger.info(
            "Application supervisor: decision=%s systemic=%s reasoning=%s",
            decision.decision.value, decision.is_systemic, decision.reasoning,
        )

        return decision

    except Exception as exc:
        logger.warning(
            "Application supervisor LLM failed (%s) — using hardcoded fallback", exc,
        )
        return _hardcoded_fallback(
            result, failed_history, remaining_count, is_quick_apply,
        )


# ---------------------------------------------------------------------------
# Helpers -- lazy imports to avoid import-time failures when browser
# deps are not installed
# ---------------------------------------------------------------------------

async def _drain_steering_commands(session_id: str) -> List[str]:
    """Return and clear queued steering messages for a session."""
    redis_client = None
    try:
        import redis.asyncio as aioredis

        settings = get_settings()
        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        key = f"steer:queue:{session_id}"
        # MULTI/EXEC prevents a concurrently queued pause/skip from being erased
        # between reading the list and deleting only the messages we received.
        async with redis_client.pipeline(transaction=True) as pipeline:
            pipeline.lrange(key, 0, -1)
            pipeline.delete(key)
            messages, _ = await pipeline.execute()
        return [m.strip() for m in messages if isinstance(m, str) and m.strip()]
    except Exception:
        logger.debug("Failed to drain steering queue for %s", session_id, exc_info=True)
        return []
    finally:
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                logger.debug("Failed to close steering queue connection", exc_info=True)


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


def _board_login_available(board: Any, user_id: Optional[str]) -> bool:
    """True when a persisted Browserbase Context holds a login for *board*.

    Only then can a board-hosted apply flow (Indeed Apply) run; otherwise the
    job is skipped as auth_required before any navigation.
    """
    if get_settings().BROWSER_MODE != "browserbase":
        return False
    key = str(getattr(board, "value", board) or "").lower()
    if not key:
        return False
    from backend.browser import browserbase_client as _bbc
    return bool(_bbc.config_for_user(user_id).context_ids.get(key))


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
        url = page.url or ""
        is_spa = "workday" in url or "myworkdayjobs" in url

        # SPAs (Workday) need extra time — the shell loads fast but content renders later
        if is_spa:
            try:
                await page.wait_for_function(
                    "() => document.body.innerText.length > 200",
                    timeout=10000,
                )
            except Exception:
                pass  # timed out — fall through to checks below

        text = await page.evaluate("() => document.body.innerText.substring(0, 1000).toLowerCase()")
        if get_settings().INDEED_ONLY:
            # Indeed's loading shell can be short; Cloudflare Ray IDs can
            # contain '404'. Neither proves that the actual job is expired.
            return any(message in text for message in (
                "this job has expired", "this job is no longer available",
                "this job has been removed", "this listing has expired",
                "this job is no longer accepting applications",
            ))
        for indicator in _NOT_FOUND_INDICATORS:
            if indicator in text:
                return True
        # Check very short pages (likely errors) — skip for SPAs that may still be loading
        if not is_spa:
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

    resume_text = (state.get("resume_text", "") if get_settings().INDEED_ONLY
                   else state.get("coached_resume") or state.get("resume_text", ""))
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

    # Salary expectation from session config
    salary_min = state.get("salary_min")
    if salary_min:
        profile["salary_expectation"] = f"${salary_min:,}"

    # LinkedIn URL
    linkedin_match = _re.search(r'linkedin\.com/in/[\w-]+', resume_text)
    if linkedin_match:
        profile["linkedin_url"] = "https://www." + linkedin_match.group(0)

    # GitHub URL
    github_match = _re.search(r'github\.com/[\w-]+', resume_text)
    if github_match:
        profile["github_url"] = "https://" + github_match.group(0)

    # Portfolio/website (non-LinkedIn, non-GitHub URLs)
    portfolio_match = _re.search(
        r'https?://(?!.*(?:linkedin|github))[\w.-]+\.\w+[/\w.-]*',
        resume_text,
    )
    if portfolio_match:
        profile["portfolio_url"] = portfolio_match.group(0)

    return profile


async def _apply_to_job(
    job_id: str,
    job: JobListing,
    state: JobHunterState,
    session_id: str,
    context: Any = None,
    stagehand: Any = None,
    employer_url: str | None = None,
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

    async def skip_easy_apply(reason):
        # Pre-navigation returns bypass the usual result writer; persist them here.
        _db_record_result(
            session_id=session_id, job_id=job_id, status="skipped",
            job_title=job.title, job_company=job.company, job_url=job.url,
            job_board=job.board.value if hasattr(job.board, "value") else str(job.board),
            job_location=job.location or "", error_message=reason,
            user_id=state.get("user_id", ""),
        )
        await emit_agent_event(session_id, "application_progress", {
            "job_id": job_id, "step": reason,
        })
        return ApplicationResult(job_id=job_id, status=ApplicationStatus.SKIPPED,
                                 error_message=reason)

    from backend.browser.indeed_policy import is_indeed_url, EASY_APPLY_SKIP_REASON
    if get_settings().INDEED_EASY_APPLY_ONLY and (employer_url or not is_indeed_url(job.url)):
        return await skip_easy_apply(EASY_APPLY_SKIP_REASON)

    if get_settings().INDEED_ONLY:
        from backend.browser.indeed_policy import is_indeed_url
        from backend.browser.application_routing import is_public_application_url
        if not is_indeed_url(job.url):
            return ApplicationResult(job_id=job_id, status=ApplicationStatus.SKIPPED,
                                     error_message="Indeed-only mode does not apply on external sites.")
        if employer_url and not is_public_application_url(employer_url):
            return ApplicationResult(job_id=job_id, status=ApplicationStatus.SKIPPED,
                                     error_message="Invalid employer application destination.")

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

    # Pre-flight: skip "Easy Apply" jobs (need board login) unless this user
    # has a persisted Browserbase login for the board.
    if getattr(job, "is_easy_apply", False) and not _board_login_available(job.board, user_id):
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

    # Pre-flight: skip jobs hosted on board domains UNLESS discovery found
    # an external ATS URL (e.g. Greenhouse/Lever). If we have an external URL,
    # swap it in so we go straight to the ATS form.
    _BOARD_GATED_DOMAINS = {"linkedin.com", "indeed.com", "glassdoor.com"}
    try:
        from urllib.parse import urlparse as _urlparse
        _host = _urlparse(job.url).hostname or ""
        if any(_host == d or _host.endswith(f".{d}") for d in _BOARD_GATED_DOMAINS):
            if getattr(job, "external_apply_url", None) and not get_settings().INDEED_ONLY:
                # Use the direct ATS URL instead of the board URL
                logger.info(
                    "Using external ATS URL for %s: %s → %s",
                    job.title, job.url[:60], job.external_apply_url[:60],
                )
                job.url = job.external_apply_url
            elif _host.endswith("indeed.com") and _board_login_available("indeed", user_id):
                # Persisted Indeed login: stay on the board and use Indeed Apply.
                logger.info("Indeed URL with persisted login — using Indeed Apply for %s", job.title)
            else:
                _board_label = next((d.split(".")[0].title() for d in _BOARD_GATED_DOMAINS if _host.endswith(d)), "Board")
                logger.info("Board-gated URL — skipping %s (%s requires login, no external link)", job.title, _board_label)
                await emit_agent_event(session_id, "application_progress", {
                    "job_id": job_id,
                    "step": f"Skipped — {_board_label} requires login (no external apply link)",
                })
                return ApplicationResult(
                    job_id=job_id,
                    status=ApplicationStatus.SKIPPED,
                    error_message="auth_required",
                    error_category=ApplicationErrorCategory.AUTH_REQUIRED,
                    duration_seconds=int(time.monotonic() - start_time),
                )
    except Exception:
        pass  # Don't block on URL parse errors

    # Pre-flight: never repeat a confirmed or uncertain submission, including Quick Apply.
    # Providing a URL does not authorize submitting the same application again.
    _app_cfg = state.get("session_config") or {}
    _app_cfg = _app_cfg if isinstance(_app_cfg, dict) else (_app_cfg.model_dump() if hasattr(_app_cfg, "model_dump") else {})
    _is_quick_apply = _app_cfg.get("discovery_mode") == "manual_urls"

    try:
        prior = check_already_applied(job_id, user_id=user_id, job_url=job.url)
    except DuplicateCheckUnavailable as exc:
        message = str(exc)
        await emit_agent_event(session_id, "application_progress", {"job_id": job_id, "step": message})
        return ApplicationResult(
            job_id=job_id, status=ApplicationStatus.FAILED,
            error_message=message, error_category=ApplicationErrorCategory.UNKNOWN,
            failure_step="duplicate_check", duration_seconds=int(time.monotonic() - start_time),
        )
    if prior:
        raw_at = prior.get("applied_at", "")
        try:
            from datetime import datetime as _dt
            applied_at = _dt.fromisoformat(raw_at).strftime("%b %d, %Y at %I:%M %p")
        except Exception:
            applied_at = raw_at or "unknown date"
        uncertain = prior.get("error_category") == ApplicationErrorCategory.SUBMISSION_UNCERTAIN.value
        category = ApplicationErrorCategory.SUBMISSION_UNCERTAIN if uncertain else None
        msg = ("A previous submission could not be verified. Check the employer or Indeed "
               "and reconcile its result before applying again." if uncertain
               else f"Already applied on {applied_at}")
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
            error_category=category.value if category else None,
            user_id=user_id,
        )
        return ApplicationResult(
            job_id=job_id,
            status=ApplicationStatus.SKIPPED,
            error_message=f"duplicate: {msg}",
            error_category=category,
            duration_seconds=int(time.monotonic() - start_time),
        )

    # Pre-flight: enforce company application rate limit (max 2 per company per 2 weeks)
    # Quick Apply bypasses this — user explicitly chose each URL
    company_limit = check_company_rate_limit(job.company, user_id=user_id) if not _is_quick_apply else None
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

        resume_text = (state.get("resume_text", "") if get_settings().INDEED_ONLY
                       else state.get("coached_resume") or state.get("resume_text", ""))
        cover_letter_template = state.get("cover_letter_template", "")

        # Compute queue progress for frontend
        _queue = state.get("application_queue", [])
        _done_ids = completed_job_ids(
            state.get("applications_submitted") or [],
            state.get("applications_failed") or [],
            state.get("applications_skipped") or [],
            state.get("active_retry_job_ids") or [],
        )
        _app_idx = len(_done_ids & set(_queue))
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

        # Record "pending" BEFORE any submission attempt so that if the process
        # is killed mid-Skyvern/API, the auto-resume won't re-submit this job.
        _db_record_result(
            session_id=session_id,
            job_id=job_id,
            status="pending",
            job_title=job.title,
            job_company=job.company,
            job_url=job.url,
            job_board=job.board.value if hasattr(job.board, "value") else str(job.board),
            job_location=job.location or "",
            user_id=user_id,
        )

        # --- Fast path: direct API submission (only if handler registered) ---
        settings = get_settings()
        from backend.browser.tools.api_applier import _ATS_HANDLERS
        if _application_policy().uses_api(job, _ATS_HANDLERS, state.get("api_failed_job_ids") or []):
            user_profile = await _extract_user_profile(state)
            resume_file = state.get("resume_file_path")

            # Generate cover letter first (needed for API submission)
            session_config = state.get("session_config")
            should_generate_cl = True
            if session_config:
                _cfg = session_config if isinstance(session_config, dict) else (session_config.model_dump() if hasattr(session_config, "model_dump") else {})
                should_generate_cl = _cfg.get("generate_cover_letters", True)

            cover_letter_text = ""
            if should_generate_cl:
                _user_email = (user_profile.get("email") or "")
                cover_letter = await generate_cover_letter(
                    job=job, resume_text=resume_text, template=cover_letter_template,
                    user_email=_user_email,
                )
                cover_letter_text = cover_letter.text

            await emit_agent_event(session_id, "application_progress", {
                "job_id": job_id,
                "step": f"Submitting via {job.ats_type.value} API for {job.title}...",
                "current": _app_idx + 1,
                "total": _total_q,
                "progress": _pct,
            })

            from backend.browser.tools.api_applier import apply_via_api
            api_result = await apply_via_api(
                job=job,
                user_profile=user_profile,
                resume_text=resume_text,
                cover_letter=cover_letter_text,
                resume_file_path=resume_file,
                session_id=session_id,
            )
            if api_result is not None:
                logger.info(
                    "API submission %s for %s at %s (took %ds)",
                    api_result.status.value, job.title, job.company,
                    api_result.duration_seconds or 0,
                )
                result = api_result
                detected_ats = api_result.ats_type or "unknown"
                result.cover_letter_used = cover_letter_text

                # Record + return — skip browser entirely
                success = result.status == ApplicationStatus.SUBMITTED
                await _record_result_to_neo4j(job_id, detected_ats, success=success)

                # SSE event
                if success:
                    await emit_agent_event(session_id, "application_submitted", {
                        "job_id": job_id, "job_title": job.title, "company": job.company,
                    })
                else:
                    _cat = result.error_category.value if result.error_category else None
                    await emit_agent_event(session_id, "application_failed", {
                        "job_id": job_id, "job_title": job.title, "company": job.company,
                        "error": result.error_message or "API submission failed",
                        "error_category": _cat,
                        "duration_seconds": result.duration_seconds,
                    })

                # Clear pending record before inserting final result
                clear_pending(session_id, job_id)

                # Persist to DB
                _tailored = state.get("tailored_resumes", {}).get(job_id)
                _tailored_text = None
                if _tailored:
                    _tailored_text = _tailored.tailored_text if hasattr(_tailored, "tailored_text") else _tailored.get("tailored_text")
                _error_cat = result.error_category.value if result.error_category else None
                _db_record_result(
                    session_id=session_id, job_id=job_id,
                    status=result.status.value, job_title=job.title,
                    job_company=job.company, job_url=job.url,
                    job_board=job.board.value if hasattr(job.board, "value") else str(job.board),
                    job_location=job.location or "", error_message=result.error_message,
                    error_category=_error_cat, ats_type=result.ats_type,
                    failure_step=result.failure_step,
                    cover_letter=cover_letter_text, tailored_resume_text=_tailored_text,
                    duration_seconds=result.duration_seconds, user_id=user_id,
                )

                # Billing
                _charge_for_application(
                    user_id=user_id, status=result.status.value,
                    job_title=job.title, job_company=job.company, job_id=job_id,
                )
                return result
            else:
                logger.info(
                    "API blocked/unavailable for %s at %s — falling back to Skyvern",
                    job.title, job.company,
                )
                # If no browser context available (API-only batch), can't fall back
                if context is None:
                    return ApplicationResult(
                        job_id=job_id,
                        status=ApplicationStatus.FAILED,
                        error_message=f"{job.ats_type.value} API blocked — no browser available for fallback",
                        error_category=ApplicationErrorCategory.CAPTCHA,
                        ats_type=f"{job.ats_type.value}_api",
                        duration_seconds=int(time.monotonic() - start_time),
                    )

        # If no browser context available (shouldn't happen for non-API jobs, but guard)
        if context is None:
            return ApplicationResult(
                job_id=job_id,
                status=ApplicationStatus.FAILED,
                error_message="No browser context available",
                duration_seconds=int(time.monotonic() - start_time),
            )

        # --- Step 1: Open tab and navigate (before cover letter to save LLM calls) ---
        use_managed_page = settings.BROWSER_MODE == "browserbase" and settings.INDEED_ONLY
        page = context.pages[0] if use_managed_page and context.pages else await context.new_page()
        if settings.BROWSER_MODE != "browserbase":
            await apply_stealth(page)

        try:
            captcha_monitor = getattr(stagehand, "_jobhunter_captcha_monitor", None)
            captcha_generation = captcha_monitor.generation if captcha_monitor else None
            # Strip tracking params from LinkedIn URLs (they can cause redirects)
            nav_url = employer_url or job.url
            if "linkedin.com/jobs/view/" in nav_url:
                from urllib.parse import urlparse, urlunparse
                parsed = urlparse(nav_url)
                nav_url = urlunparse(parsed._replace(query=""))
                logger.info("Cleaned LinkedIn URL: %s", nav_url)
            await page.goto(nav_url, wait_until="domcontentloaded", timeout=90000)
            await asyncio.sleep(2)  # settle
            if settings.INDEED_EASY_APPLY_ONLY:
                from backend.browser.indeed_policy import is_indeed_url, EASY_APPLY_SKIP_REASON
                redirect = getattr(context, '_jobhunter_external_redirect', None)
                if is_indeed_url(job.url) and (not is_indeed_url(page.url) or isinstance(redirect, str)):
                    return await skip_easy_apply(EASY_APPLY_SKIP_REASON)
            if settings.INDEED_ONLY and not employer_url:
                from backend.browser.indeed_policy import wait_for_indeed_page
                await wait_for_indeed_page(
                    page, captcha_monitor=captcha_monitor,
                    since_generation=captcha_generation,
                )
            logger.info("Final page URL after navigation: %s", page.url)

            # Skyvern handles CAPTCHAs natively — no manual intervention needed.
            # Just log if one is detected for debugging purposes.
            if await _has_captcha(page):
                logger.info("CAPTCHA detected on %s — Skyvern will handle it", job.url[:80])

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
                if settings.INDEED_EASY_APPLY_ONLY and job.board == JobBoard.INDEED:
                    from backend.browser.indeed_policy import EASY_APPLY_LOGIN_SKIP_REASON
                    return await skip_easy_apply(EASY_APPLY_LOGIN_SKIP_REASON)
                logger.info("Login required (%s) for %s — skipping", final_url, job.title)
                await emit_agent_event(session_id, "application_progress", {
                    "job_id": job_id,
                    "step": f"Skipped — {job.board.value} requires login",
                })
                return ApplicationResult(
                    job_id=job_id,
                    status=ApplicationStatus.SKIPPED,
                    error_message="auth_required",
                    error_category=ApplicationErrorCategory.AUTH_REQUIRED,
                    duration_seconds=int(time.monotonic() - start_time),
                )

            # --- Step 1c: Check for external apply link ---
            # Many board pages (LinkedIn, ZipRecruiter, etc.) have an
            # "Apply on company site" link that goes to an external ATS
            # (Greenhouse, Lever, Workday).  Follow it if found.
            # Skip if already on an ATS domain (avoid leaving a form page).
            current_lower = page.url.lower()
            already_on_ats = any(d in current_lower for d in _EXTERNAL_ATS_DOMAINS)
            external_url = None if already_on_ats or get_settings().INDEED_ONLY else await _find_external_apply_link(page)
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
                if settings.INDEED_EASY_APPLY_ONLY and job.board == JobBoard.INDEED:
                    from backend.browser.indeed_policy import EASY_APPLY_LOGIN_SKIP_REASON
                    return await skip_easy_apply(EASY_APPLY_LOGIN_SKIP_REASON)
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
                _cl_profile = await _extract_user_profile(state)
                cover_letter = await generate_cover_letter(
                    job=job,
                    resume_text=resume_text,
                    template=cover_letter_template,
                    user_email=_cl_profile.get("email", ""),
                )
                cover_letter_text = cover_letter.text

            # --- Step 3: Extract user profile ---
            user_profile = await _extract_user_profile(state)
            resume_file = state.get("resume_file_path")

            # --- Step 4: Apply via Playwright + Claude Haiku ---
            # Uses ATS-specific appliers (Greenhouse, Lever, Ashby) with
            # form_filler.py for Claude-powered field extraction and filling.
            await emit_agent_event(session_id, "application_progress", {
                "job_id": job_id,
                "step": f"Filling application form for {job.title}...",
                "current": _app_idx + 1,
                "total": _total_q,
                "progress": _pct,
            })

            from backend.browser.tools.appliers.dispatcher import apply_with_playwright
            from backend.shared.application_rules import load_application_rules
            result = await apply_with_playwright(
                job=job,
                user_profile=user_profile,
                resume_text=resume_text,
                cover_letter=cover_letter_text,
                resume_file_path=resume_file,
                session_id=session_id,
                page=page,
                application_rules=load_application_rules(user_id),
                stagehand=stagehand,
                employer_site=bool(employer_url),
            )

        finally:
            if page and not page.is_closed() and not use_managed_page:
                await page.close()

        if (get_settings().INDEED_EASY_APPLY_ONLY
                and result.status == ApplicationStatus.QUEUED and result.external_application_url):
            from backend.browser.indeed_policy import EASY_APPLY_SKIP_REASON
            result.status = ApplicationStatus.SKIPPED
            result.error_message = EASY_APPLY_SKIP_REASON
            result.external_application_url = None

        if result.status == ApplicationStatus.QUEUED and result.external_application_url:
            clear_pending(session_id, job_id)
            await emit_agent_event(session_id, "application_progress", {
                "job_id": job_id,
                "step": f"Queued employer-site application for {job.title} at {job.company}.",
            })
            return result

        # --- Step 8: Record to Neo4j ---
        success = result.status == ApplicationStatus.SUBMITTED
        await _record_result_to_neo4j(job_id, detected_ats, success=success)

        # Emit final SSE event
        if success:
            _label = f"{job.title} at {job.company}" if job.company else job.title
            await emit_agent_event(session_id, "application_submitted", {
                "job_id": job_id,
                "job_title": job.title,
                "company": job.company,
                "message": f"Applied to {_label}",
            })
        elif result.status == ApplicationStatus.SKIPPED:
            await emit_agent_event(session_id, "application_progress", {
                "job_id": job_id, "step": result.error_message or "Application skipped.",
            })
        else:
            _label = f"{job.title} at {job.company}" if job.company else job.title
            await emit_agent_event(session_id, "application_failed", {
                "job_id": job_id,
                "job_title": job.title,
                "company": job.company,
                "message": f"Failed: {_label}",
                "error": result.error_message or "Application did not complete",
                "screenshot_url": result.screenshot_url,
                "error_category": (
                    result.error_category.value if result.error_category
                    else (_infer_error_category(result.error_message).value
                          if _infer_error_category(result.error_message) else None)
                ),
                "duration_seconds": result.duration_seconds,
            })

        # Always clear pending before inserting the final result row.
        # Previously we kept pending for "ambiguous" Skyvern errors, but since
        # we always insert a final failed row below, keeping pending just
        # creates duplicate rows (pending + failed) and inflates the UI count.
        clear_pending(session_id, job_id)

        # Persist to DB immediately (survives restarts)
        # Always store the cover letter and tailored resume regardless of success/failure
        _tailored = state.get("tailored_resumes", {}).get(job_id)
        _tailored_text = None
        if _tailored:
            _tailored_text = _tailored.tailored_text if hasattr(_tailored, "tailored_text") else _tailored.get("tailored_text")
        # Infer error category from result
        _error_cat = (
            result.error_category.value if result.error_category
            else (_infer_error_category(result.error_message).value if _infer_error_category(result.error_message) else None)
        )
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
            error_category=_error_cat,
            ats_type=result.ats_type,
            failure_step=result.failure_step,
            cover_letter=result.cover_letter_used or cover_letter_text,
            tailored_resume_text=_tailored_text,
            duration_seconds=result.duration_seconds,
            screenshot_path=result.screenshot_url,
            user_id=user_id,
        )

        # Auto-blocklist companies whose TOTP we can't retrieve
        # Skip ATS platforms / job aggregators that appear as "company" due to scraper noise
        _ATS_PLATFORMS = {"greenhouse", "lever", "aplitrak", "jobgether", "workday", "icims",
                          "smartrecruiters", "jobs", "all openings", "taleo", "brassring"}
        _final_cat = result.error_category or _infer_error_category(result.error_message)
        if _final_cat == ApplicationErrorCategory.TOTP_REQUIRED and job.company:
            _company_lower = job.company.lower().strip()
            if _company_lower in _ATS_PLATFORMS:
                logger.info("Skipping auto-blocklist for ATS platform name: %s", job.company)
            else:
                try:
                    from backend.shared.billing_store import get_blocked_companies, update_blocked_companies
                    blocked = get_blocked_companies(user_id)
                    if _company_lower not in blocked:
                        blocked.add(_company_lower)
                        update_blocked_companies(user_id, list(blocked))
                        logger.info(
                            "Auto-blocklisted %s — TOTP verification failed, will skip in future sessions",
                            job.company,
                        )
                except Exception:
                    logger.warning("Failed to auto-blocklist %s", job.company, exc_info=True)

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

        _label = f"{job.title} at {job.company}" if job.company else job.title
        await emit_agent_event(session_id, "application_failed", {
            "job_id": job_id,
            "job_title": job.title,
            "company": job.company,
            "message": f"Failed: {_label}",
            "error": str(exc),
        })

        # Always clear pending before inserting the final failed row.
        clear_pending(session_id, job_id)

        _exc_category = _infer_error_category(str(exc))
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
            error_category=_exc_category.value if _exc_category else None,
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

    The graph loops this node between jobs so the workflow supervisor
    can authoritatively steer the run after every application attempt.

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
    employer_queue = dict(state.get("employer_application_queue") or {})
    questions = dict(state.get("application_questions") or {})
    consecutive_failures: int = state.get("consecutive_failures", 0)
    session_id: str = state.get("session_id", "unknown")
    user_id: str = state.get("user_id", "")
    api_failed_ids = set(state.get("api_failed_job_ids") or [])

    manager: Optional[BrowserManager] = None
    pause_result: ApplicationResult | None = None
    pause_supervisor: ApplicationSupervisorResult | None = None

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
                "active_retry_job_ids": [],
            }

        done_ids = completed_job_ids(
            state.get("applications_submitted") or [],
            state.get("applications_failed") or [],
            state.get("applications_skipped") or [],
            state.get("active_retry_job_ids") or [],
        )

        # Track companies already applied to in this session (1 per company)
        session_applied_companies: set = set()
        for r in (state.get("applications_submitted") or []):
            job_for_r = _find_job_in_state(r.job_id, state)
            if job_for_r:
                session_applied_companies.add(job_for_r.company.lower().strip())

        from backend.browser.application_routing import ordered_pending_jobs
        remaining = ordered_pending_jobs(application_queue, done_ids, employer_queue)
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
                "active_retry_job_ids": [],
            }

        logger.info(
            "Application agent starting -- %d jobs pending of %d total",
            len(remaining),
            len(application_queue),
        )
        total_in_queue = len(application_queue)
        processed_count = len(done_ids & set(application_queue))
        app_idx = processed_count
        job_id = remaining[0]
        pct = int((app_idx / total_in_queue) * 100) if total_in_queue else 0
        job_obj = _find_job_in_state(job_id, state)
        job_label = f"{job_obj.title} at {job_obj.company}" if job_obj else job_id[:8]

        from backend.browser.indeed_policy import EASY_APPLY_SKIP_REASON, is_indeed_url
        skip_employer = get_settings().INDEED_EASY_APPLY_ONLY and (
            job_id in employer_queue or (job_obj is not None and not is_indeed_url(job_obj.url)))
        skip_reason = EASY_APPLY_SKIP_REASON if skip_employer else "skipped_by_workflow_supervisor"
        if skip_employer and job_id in employer_queue:
            employer_queue[job_id] = {**employer_queue[job_id], "status": "skipped", "reason": skip_reason}
        if state.get("skip_next_job_requested") or skip_employer:
            skipped_result = ApplicationResult(
                job_id=job_id,
                status=ApplicationStatus.SKIPPED,
                error_message=skip_reason,
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
                    error_message=skip_reason,
                    user_id=user_id,
                )
            await emit_agent_event(session_id, "application_progress", {
                "step": f"Skipped {job_label}: {skip_reason}",
                "progress": pct,
                "current": app_idx + 1,
                "total": total_in_queue,
            })
            return {
                "applications_submitted": [],
                "applications_failed": [],
                "applications_skipped": [job_id],
                "employer_application_queue": employer_queue,
                "consecutive_failures": 0,
                "status": "applying",
                "agent_statuses": {"application": f"skipped -- {job_label}"},
                "errors": [],
                "skip_next_job_requested": False,
                "active_retry_job_ids": [],
            }

        # --- Per-session company dedup (1 application per company) ---
        # Quick Apply bypasses this — user explicitly chose each URL
        _qa_cfg = state.get("session_config") or {}
        _qa_cfg = _qa_cfg if isinstance(_qa_cfg, dict) else (_qa_cfg.model_dump() if hasattr(_qa_cfg, "model_dump") else {})
        _qa_mode = _qa_cfg.get("discovery_mode") == "manual_urls"
        if not _qa_mode and job_obj and job_obj.company.lower().strip() in session_applied_companies:
            company_name = job_obj.company
            logger.info("Skipping %s — already applied to %s in this session", job_label, company_name)
            skipped_result = ApplicationResult(
                job_id=job_id,
                status=ApplicationStatus.SKIPPED,
                error_message=f"Already applied to {company_name} in this session",
                duration_seconds=0,
            )
            skipped.append(skipped_result)
            _db_record_result(
                session_id=session_id, job_id=job_id, status="skipped",
                job_title=job_obj.title, job_company=job_obj.company,
                job_url=job_obj.url,
                job_board=job_obj.board.value if hasattr(job_obj.board, "value") else str(job_obj.board),
                job_location=job_obj.location or "",
                error_message=f"Already applied to {company_name} in this session",
                user_id=user_id,
            )
            await emit_agent_event(session_id, "application_progress", {
                "step": f"Skipped {job_label} (already applied to {company_name})",
                "progress": pct, "current": app_idx + 1, "total": total_in_queue,
            })
            return {
                "applications_submitted": [], "applications_failed": [],
                "applications_skipped": [job_id],
                "consecutive_failures": 0, "status": "applying",
                "agent_statuses": {"application": f"skipped -- duplicate company {company_name}"},
                "errors": [], "skip_next_job_requested": False,
                "active_retry_job_ids": [],
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

        # --- Batch API-eligible jobs (fast path, ~3s each) ---
        # Failed API attempts use the browser directly on subsequent turns.
        policy = _application_policy()
        api_jobs: list[ApplicationCandidate] = []
        browser_jobs: list[ApplicationCandidate] = []
        # Only route to API if there's actually a registered handler
        from backend.browser.tools.api_applier import _ATS_HANDLERS
        for jid in remaining:
            j = _find_job_in_state(jid, state)
            if j is None:
                continue
            if policy.uses_api(j, _ATS_HANDLERS, api_failed_ids):
                api_jobs.append((jid, j))
            else:
                browser_jobs.append((jid, j))

        # Process API jobs in parallel (no browser needed)
        if api_jobs:
            # Deduplicate: at most one job per company in each batch to avoid
            # TOCTOU race in the per-company rate limit check during gather().
            batch, deferred_batch = select_company_batch(api_jobs, settings.API_APPLY_BATCH_SIZE)
            # Put deferred same-company jobs back for next iteration
            if deferred_batch:
                logger.info(
                    "Deferred %d jobs to avoid same-company race condition in batch",
                    len(deferred_batch),
                )
                browser_jobs.extend(deferred_batch)
            logger.info(
                "Batching %d API-eligible jobs in parallel (Greenhouse/Lever)",
                len(batch),
            )
            api_tasks = [
                _apply_to_job(jid, j, state, session_id, context=None)
                for jid, j in batch
            ]
            api_results = await asyncio.gather(*api_tasks, return_exceptions=True)
            for (jid, j), res in zip(batch, api_results):
                if isinstance(res, BaseException):
                    if not isinstance(res, Exception):
                        raise res
                    # The transport may have sent the POST before raising. An
                    # unclassified exception is not permission to submit again.
                    res = ApplicationResult(
                        job_id=jid, status=ApplicationStatus.FAILED,
                        error_category=ApplicationErrorCategory.SUBMISSION_UNCERTAIN,
                        error_message="API delivery could not be determined; reconcile before retrying.",
                        failure_step="submit",
                    )
                    _db_record_result(
                        session_id=session_id, job_id=jid, status="failed",
                        job_title=j.title, job_company=j.company, job_url=j.url,
                        job_board=j.board.value, job_location=j.location or "",
                        error_message=res.error_message, error_category=res.error_category.value,
                        user_id=user_id,
                    )
                outcome = classify_outcome(res, source="api")
                if outcome is OutcomeKind.BROWSER_FALLBACK:
                    browser_jobs.append((jid, j))
                    api_failed_ids.add(jid)
                elif outcome is OutcomeKind.SUBMITTED:
                    submitted.append(res)
                    consecutive_failures = 0
                elif outcome is OutcomeKind.FAILED:
                    failed.append(res)
                    if requires_explicit_pause(res) and pause_supervisor is None:
                        pause_result = res
                        pause_supervisor = await _call_application_supervisor(
                            res, list(state.get("applications_failed") or []) + failed,
                            len(remaining) - len(batch), _qa_mode, session_id,
                        )
                else:
                    skipped.append(res)
                    consecutive_failures = 0

        browser_batch, _ = select_company_batch(browser_jobs, policy.browser_batch_size)
        if browser_batch and pause_supervisor is None:
            job_id, job = browser_batch[0]
            manager = BrowserManager()
            await manager.start_for_task(
                board=job.board,
                purpose="apply_external" if job_id in employer_queue else "apply",
                headless=settings.BROWSER_HEADLESS,
                user_id=state.get("user_id"),
            )
            _, context = await manager.new_context()
            if manager.live_view_url:
                await emit_agent_event(session_id, "browser_live_view", {
                    "url": manager.live_view_url,
                    "provider": "browserbase",
                    "browserbase_session_id": manager.browserbase_session_id,
                    "job_id": job_id,
                })

            # Stagehand owns a single managed tab. Legacy concurrent browser
            # jobs retain their individual pages; Indeed is always a batch of one.
            browser_results = await asyncio.gather(*(
                _apply_to_job(
                    job_id=jid, job=j, state={**state, "api_failed_job_ids": list(api_failed_ids)},
                    session_id=session_id, context=context,
                    stagehand=manager.stagehand if len(browser_batch) == 1 else None,
                    employer_url=(employer_queue.get(jid) or {}).get("url"),
                ) for jid, j in browser_batch
            ), return_exceptions=True)

            pause_result = select_explicit_pause(browser_results)
            if pause_result is not None:
                pause_supervisor = await _call_application_supervisor(
                    result=pause_result, failed_history=failed,
                    remaining_count=max(0, len(remaining) - len(browser_batch)),
                    is_quick_apply=_qa_mode, session_id=session_id,
                )

            # One outcome path for every batch size preserves questions,
            # employer handoffs and safety interrupts in legacy modes too.
            for index, ((job_id, job), result) in enumerate(zip(browser_batch, browser_results)):
                if isinstance(result, BaseException):
                    if not isinstance(result, Exception):
                        raise result  # cancellation is control flow, never a failed job
                    error_msg = f"Application failed for job {job_id}: {result}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    failed.append(ApplicationResult(
                        job_id=job_id, status=ApplicationStatus.FAILED,
                        error_message=str(result),
                    ))
                    consecutive_failures += 1
                    _db_record_result(
                        session_id=session_id, job_id=job_id,
                        status="failed", job_title=job.title,
                        job_company=job.company, job_url=job.url,
                        job_board=job.board.value if hasattr(job.board, "value") else str(job.board),
                        job_location=job.location or "",
                        error_message=str(result), user_id=user_id,
                    )
                    continue

                outcome = classify_outcome(result)
                if result.status != ApplicationStatus.QUEUED and job_id in employer_queue:
                    employer_queue[job_id] = {**employer_queue[job_id], "status": result.status.value}
                if outcome is OutcomeKind.HANDOFF:
                    employer_queue[job_id] = {
                        "url": result.external_application_url, "source_url": job.url,
                        "title": job.title, "company": job.company, "status": "queued",
                    }
                    consecutive_failures = 0
                elif outcome is OutcomeKind.SUBMITTED:
                    submitted.append(result)
                    consecutive_failures = 0
                elif outcome is OutcomeKind.FAILED:
                    failed.append(result)
                    if pause_supervisor is None:
                        supervisor = await _call_application_supervisor(
                            result=result,
                            failed_history=list(state.get("applications_failed") or []) + failed,
                            remaining_count=max(0, len(remaining) - index - 1),
                            is_quick_apply=_qa_mode,
                            session_id=session_id,
                        )
                        consecutive_failures = consecutive_failures + 1 if supervisor.is_systemic else 0
                        if supervisor.decision in (SupervisorDecision.PAUSE, SupervisorDecision.ABORT):
                            pause_result, pause_supervisor = result, supervisor
                    # Collect every already-running member before returning a
                    # pause. Deterministic safety stops outrank ordinary pauses.
                    if result.error_message:
                        errors.append(f"Application failed for {job_id}: {result.error_message}")
                else:
                    skipped.append(result)
                    if outcome is OutcomeKind.NEEDS_INPUT:
                        questions[job_id] = {
                            "question": result.error_message or "Required answer missing.",
                            "title": job.title, "company": job.company,
                            "source_url": job.url,
                            "application_url": (employer_queue.get(job_id) or {}).get("url", job.url),
                        }
                    consecutive_failures = 0

        if pause_supervisor is not None:
            return {
                "applications_submitted": submitted,
                "applications_failed": failed,
                "applications_skipped": [r.job_id for r in skipped],
                "consecutive_failures": MAX_CONSECUTIVE_FAILURES,
                "status": "paused",
                "agent_statuses": {"application": f"paused — {pause_supervisor.reasoning}"},
                "errors": errors,
                "skip_next_job_requested": False,
                "active_retry_job_ids": [],
                "api_failed_job_ids": list(api_failed_ids),
                "employer_application_queue": employer_queue,
                "application_questions": questions,
                **({
                    "pause_requested": True,
                    "status_before_pause": "applying",
                    "pause_resume_node": "application",
                    "pending_supervisor_response": pause_supervisor.reasoning,
                } if pause_result is not None and requires_explicit_pause(pause_result) else {}),
            }

        # Summary
        total_processed = len(submitted) + len(failed) + len(skipped)
        done_pct = int(((processed_count + total_processed) / total_in_queue) * 100) if total_in_queue else 0
        status_label = (
            f"{len(submitted)} submitted, {len(failed)} failed"
            f"{f', {len(skipped)} skipped' if skipped else ''}"
        )
        await emit_agent_event(session_id, "application_progress", {
            "step": status_label,
            "progress": done_pct,
            "submitted": len(state.get("applications_submitted") or []) + len(submitted),
            "failed": len(state.get("applications_failed") or []) + len(failed),
            "skipped": len(state.get("applications_skipped") or []) + len(skipped),
            "employer_application_queue": employer_queue,
            "application_questions": questions,
        })

        agent_status = f"processed -- {total_processed} jobs ({status_label})"

    except Exception as exc:
        logger.exception("Application agent failed")
        errors.append(f"Application agent error: {exc}")
        agent_status = f"failed -- {exc}"

    finally:
        if manager:
            try:
                if manager.browserbase_session_id:
                    await emit_agent_event(session_id, "browser_live_view_ended", {
                        "browserbase_session_id": manager.browserbase_session_id,
                    })
            except Exception:
                pass
            try:
                await manager.stop()
            except Exception:
                pass
        try:
            from backend.orchestrator.agents._login_sync import cleanup as _cleanup_login

            _cleanup_login(session_id)
        except Exception:
            pass

    # Feed anonymized results to Moltbook performance tracker
    try:
        from backend.moltbook.feedback_loop import record_application_result
        for r in submitted:
            record_application_result(
                board=getattr(r, "board", "") or "",
                ats_type=getattr(r, "ats_type", "") or "",
                success=True,
            )
        for r in failed:
            record_application_result(
                board=getattr(r, "board", "") or "",
                ats_type=getattr(r, "ats_type", "") or "",
                success=False,
                blocker=getattr(r, "error_category", "") or "",
            )
    except Exception:
        pass  # Moltbook feedback is best-effort

    return {
        "applications_submitted": submitted,
        "applications_failed": failed,
        "applications_skipped": [r.job_id for r in skipped],
        "consecutive_failures": consecutive_failures,
        "status": "applying",
        "agent_statuses": {"application": agent_status},
        "errors": errors,
        "skip_next_job_requested": False,
        "api_failed_job_ids": list(api_failed_ids),
        "active_retry_job_ids": [],
        "employer_application_queue": employer_queue,
        "application_questions": questions,
    }


# ---------------------------------------------------------------------------
# Alias for graph.py compatibility
# ---------------------------------------------------------------------------
run = run_application_agent
