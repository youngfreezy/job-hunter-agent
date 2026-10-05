"""Pure application decisions agree across planning, execution and graph routing."""

from dataclasses import replace

import pytest

from backend.orchestrator.application_policy import (
    ApplicationPolicy, OutcomeKind, classify_outcome, completed_job_ids,
    select_company_batch, select_retry_jobs,
)
from backend.shared.models.schemas import (
    ApplicationErrorCategory as Error, ApplicationResult, ApplicationStatus as Status,
    ATSType, JobBoard, JobListing,
)


def job(job_id="job", company="Acme"):
    return JobListing(id=job_id, title="Engineer", company=company, location="Remote", url="https://example.com/job",
                      board=JobBoard.INDEED, ats_type=ATSType.GREENHOUSE)


def result(job_id, category=Error.FORM_NAVIGATION, status=Status.FAILED):
    return ApplicationResult(job_id=job_id, status=status, error_category=category)


def test_api_requires_every_guard_and_registered_handler():
    policy = ApplicationPolicy(api_enabled=True, indeed_only=False, easy_apply_only=False, browser_concurrency=3)
    assert policy.uses_api(job(), {ATSType.GREENHOUSE}, set())
    assert not policy.uses_api(job(), set(), set())
    assert not policy.uses_api(job(), {ATSType.GREENHOUSE}, {"job"})
    for guard in ({"api_enabled": False}, {"indeed_only": True}, {"easy_apply_only": True}):
        assert not replace(policy, **guard).uses_api(job(), {ATSType.GREENHOUSE}, set())
    assert replace(policy, indeed_only=True).browser_batch_size == 1
    assert replace(policy, easy_apply_only=True).browser_batch_size == 1
    assert policy.browser_batch_size == 3


def test_company_batch_preserves_slice_order_and_defers_duplicates_without_mutation():
    candidates = [("1", job("1", " Acme ")), ("2", job("2", "acme")), ("3", job("3", "Other"))]
    selected, deferred = select_company_batch(candidates, limit=2)
    assert [jid for jid, _ in selected] == ["1"]
    assert [jid for jid, _ in deferred] == ["2"]
    assert len(candidates) == 3  # third job waits for the next graph turn


@pytest.mark.parametrize("source", ["browser", "api"])
def test_uncertain_submission_and_budget_never_become_browser_fallback(source):
    uncertain = result("job", Error.SUBMISSION_UNCERTAIN)
    budget = result("job").model_copy(update={"failure_step": "model_budget"})
    assert classify_outcome(uncertain, source=source) is OutcomeKind.FAILED
    assert classify_outcome(budget, source=source) is OutcomeKind.FAILED


def test_outcome_distinguishes_handoff_question_and_safe_api_fallback():
    handoff = result("job", status=Status.QUEUED).model_copy(update={"external_application_url": "https://example.com/apply"})
    question = result("job", Error.NEEDS_INPUT, Status.SKIPPED)
    assert classify_outcome(handoff) is OutcomeKind.HANDOFF
    assert classify_outcome(question) is OutcomeKind.NEEDS_INPUT
    assert classify_outcome(result("job"), source="api") is OutcomeKind.BROWSER_FALLBACK


def test_retry_request_never_reopens_a_receipt_or_uncertain_outcome():
    completed = completed_job_ids(
        [result("submitted", status=Status.SUBMITTED)],
        [result("uncertain", Error.SUBMISSION_UNCERTAIN), result("retryable")],
        ["skipped"], {"submitted", "uncertain", "retryable", "skipped"},
    )
    assert completed == {"submitted", "uncertain", "skipped"}


def test_retry_selection_only_uses_latest_failure_and_preserves_caller_counts():
    failures = [result("uncertain"), result("retryable"), result("uncertain", Error.SUBMISSION_UNCERTAIN), result("spent")]
    counts = {"spent": 1}
    selected, updated = select_retry_jobs(failures, eligible_ids={"uncertain", "retryable", "spent"},
        excluded_ids=set(), retry_counts=counts, limit=2)
    assert selected == ["retryable"]
    assert updated == {"spent": 1, "retryable": 1}
    assert counts == {"spent": 1}


def test_retry_selection_honors_capacity_and_eligibility():
    failures = [result("eligible"), result("ineligible"), result("already-done")]
    selected, _ = select_retry_jobs(failures, eligible_ids={"eligible", "already-done"},
        excluded_ids={"already-done"}, retry_counts={}, limit=1)
    assert selected == ["eligible"]
    assert select_retry_jobs(failures, eligible_ids={"eligible"}, excluded_ids=set(), retry_counts={}, limit=0) == ([], {})
