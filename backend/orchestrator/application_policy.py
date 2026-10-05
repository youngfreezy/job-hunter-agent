"""Pure decisions shared by application planning, execution and graph routing.

No settings, storage, browser or model access belongs here. The orchestrator
supplies a policy snapshot and performs the I/O implied by each outcome.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from itertools import takewhile
from typing import Literal

from pydantic import BaseModel, Field

from backend.shared.models.schemas import (
    ApplicationErrorCategory as Error,
    ApplicationResult,
    ApplicationStatus as Status,
    ATSType,
    JobListing,
)

MAX_CONSECUTIVE_FAILURES = 3
MAX_RETRY_PER_JOB = 1
RETRYABLE_ERROR_CATEGORIES = frozenset({
    Error.FORM_NAVIGATION, Error.FORM_FILL_ERROR, Error.SUBMIT_FAILED,
    Error.NO_CONFIRMATION, Error.TIMEOUT, Error.UNKNOWN,
})
_EXPLICIT_PAUSE_STEPS = frozenset({"model_budget", "duplicate_check"})
_NO_AUTOMATIC_RETRY = frozenset({Error.SUBMISSION_UNCERTAIN})
ApplicationCandidate = tuple[str, JobListing]

# Priority matters: e.g. verification at login is TOTP, not generic auth.
_ERROR_PATTERNS: tuple[tuple[Error, tuple[str, ...]], ...] = (
    (Error.TOTP_REQUIRED, ("totp", "verification code", "2fa", "two-factor", "one-time")),
    (Error.AUTH_REQUIRED, ("auth", "login", "sign in", "easy apply", "sign_in")),
    (Error.JOB_EXPIRED, ("expired", "removed", "no longer", "404", "not found", "job_expired")),
    (Error.CAPTCHA, ("captcha", "recaptcha")),
    (Error.TIMEOUT, ("timeout", "timed out")),
    (Error.CREDIT_INSUFFICIENT, ("insufficient_credits", "credit")),
    (Error.DUPLICATE, ("duplicate", "already applied")),
    (Error.RATE_LIMITED, ("rate limit", "rate_limit")),
    (Error.NO_CONFIRMATION, ("confirmation", "no_confirmation")),
    (Error.SUBMIT_FAILED, ("submit", "button")),
    (Error.FORM_FILL_ERROR, ("form", "field", "fill")),
    (Error.FORM_NAVIGATION, ("navigate", "navigation", "element", "selector")),
)
_SITE_BLOCKERS = frozenset({Error.CAPTCHA, Error.AUTH_REQUIRED, Error.JOB_EXPIRED, Error.DUPLICATE})


class SupervisorDecision(str, Enum):
    CONTINUE = "continue"
    PAUSE = "pause"
    ABORT = "abort"


class ApplicationSupervisorResult(BaseModel):
    decision: SupervisorDecision = Field(description="What to do next after this failure")
    reasoning: str = Field(description="1-2 sentence explanation for logging")
    is_systemic: bool = Field(
        default=False, description="True if this failure suggests a systemic issue, not job-specific",
    )


def infer_error_category(message: str | None) -> Error | None:
    if not message:
        return None
    text = message.lower()
    return next((category for category, patterns in _ERROR_PATTERNS
                 if any(pattern in text for pattern in patterns)), Error.UNKNOWN)


def is_systemic_failure(result: ApplicationResult) -> bool:
    return (result.error_category or infer_error_category(result.error_message)) not in _SITE_BLOCKERS


def fallback_supervisor_decision(
    result: ApplicationResult, failed_history: Sequence[ApplicationResult],
    remaining_count: int, is_quick_apply: bool,
) -> ApplicationSupervisorResult:
    """Deterministic fallback for unavailable models, with the same streak policy."""
    consecutive = sum(1 for _ in takewhile(is_systemic_failure, reversed(failed_history)))
    if consecutive >= (5 if is_quick_apply else MAX_CONSECUTIVE_FAILURES):
        return ApplicationSupervisorResult(
            decision=SupervisorDecision.PAUSE,
            reasoning=f"Fallback: {consecutive} consecutive systemic failures", is_systemic=True,
        )
    return ApplicationSupervisorResult(
        decision=SupervisorDecision.CONTINUE,
        reasoning="Fallback: failure appears job-specific, continuing",
        is_systemic=is_systemic_failure(result),
    )


@dataclass(frozen=True)
class ApplicationPolicy:
    api_enabled: bool
    indeed_only: bool
    easy_apply_only: bool
    browser_concurrency: int

    @property
    def browser_batch_size(self) -> int:
        # Indeed shares a managed tab and auth context: never race two forms.
        return 1 if self.indeed_only or self.easy_apply_only else self.browser_concurrency

    def uses_api(
        self, job: JobListing, registered_handlers: Collection[ATSType],
        previously_failed_ids: Collection[str],
    ) -> bool:
        return (
            self.api_enabled and not self.indeed_only and not self.easy_apply_only
            and job.ats_type in registered_handlers
            and str(job.id) not in previously_failed_ids
        )


class OutcomeKind(str, Enum):
    SUBMITTED = "submitted"
    FAILED = "failed"
    SKIPPED = "skipped"
    NEEDS_INPUT = "needs_input"
    HANDOFF = "handoff"
    BROWSER_FALLBACK = "browser_fallback"


def requires_explicit_pause(result: ApplicationResult) -> bool:
    """A budget/history stop cannot be overridden by another paid supervisor."""
    return result.failure_step in _EXPLICIT_PAUSE_STEPS


def select_explicit_pause(results: Sequence[ApplicationResult | BaseException]) -> ApplicationResult | None:
    """Known batch safety stops take priority over any model adjudication."""
    return next((result for result in results
                 if isinstance(result, ApplicationResult) and requires_explicit_pause(result)), None)


def classify_outcome(
    result: ApplicationResult, *, source: Literal["api", "browser"] = "browser",
) -> OutcomeKind:
    if result.status == Status.SUBMITTED:
        return OutcomeKind.SUBMITTED
    if result.status == Status.QUEUED and result.external_application_url:
        return OutcomeKind.HANDOFF
    if result.status == Status.FAILED:
        if source == "api" and not requires_explicit_pause(result) and result.error_category not in _NO_AUTOMATIC_RETRY:
            return OutcomeKind.BROWSER_FALLBACK
        return OutcomeKind.FAILED
    if result.error_category == Error.NEEDS_INPUT:
        return OutcomeKind.NEEDS_INPUT
    return OutcomeKind.SKIPPED


def select_company_batch(
    candidates: Sequence[ApplicationCandidate], limit: int,
) -> tuple[list[ApplicationCandidate], list[ApplicationCandidate]]:
    """Select within the current slice; defer duplicates to avoid admission races."""
    selected: list[ApplicationCandidate] = []
    deferred: list[ApplicationCandidate] = []
    seen: set[str] = set()
    for candidate in candidates[:limit]:
        company = candidate[1].company.lower().strip()
        if company in seen:
            deferred.append(candidate)
        else:
            seen.add(company)
            selected.append(candidate)
    return selected, deferred


def completed_job_ids(
    submitted: Sequence[ApplicationResult], failed: Sequence[ApplicationResult],
    skipped: Collection[str], active_retry_ids: Collection[str] = (),
) -> set[str]:
    """A retry request may reopen failures, never a receipt or delivery hold."""
    failed_ids = {result.job_id for result in failed}
    uncertain_ids = {result.job_id for result in failed if result.error_category in _NO_AUTOMATIC_RETRY}
    return (
        {result.job_id for result in submitted}
        | (failed_ids - set(active_retry_ids)) | uncertain_ids | set(skipped)
    )


def select_retry_jobs(
    failures: Sequence[ApplicationResult], *, eligible_ids: Collection[str],
    excluded_ids: Collection[str], retry_counts: Mapping[str, int], limit: int,
) -> tuple[list[str], dict[str, int]]:
    """Retry only the latest eligible outcome, with bounded attempts and capacity."""
    selected: list[str] = []
    counts = dict(retry_counts)
    seen: set[str] = set(excluded_ids)
    for failure in reversed(failures):
        if len(selected) >= limit:
            break
        job_id = failure.job_id
        if job_id in seen:
            continue
        seen.add(job_id)
        if (job_id in eligible_ids and counts.get(job_id, 0) < MAX_RETRY_PER_JOB
                and failure.error_category in RETRYABLE_ERROR_CATEGORIES):
            selected.append(job_id)
            counts[job_id] = counts.get(job_id, 0) + 1
    return selected, counts
