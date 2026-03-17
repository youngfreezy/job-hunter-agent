# Copyright (c) 2026 V2 Software LLC. All rights reserved.

from datetime import datetime

import pytest

from backend.orchestrator.pipeline.graph import auto_approve_gate, route_after_qa
from backend.shared.models.schemas import (
    ApplicationErrorCategory,
    ApplicationResult,
    ApplicationStatus,
    ATSType,
    JobBoard,
    JobListing,
    ScoredJob,
)


def _job(job_id: str, title: str = "Engineer", company: str = "Acme") -> JobListing:
    return JobListing(
        id=job_id,
        title=title,
        company=company,
        location="Remote",
        url=f"https://example.com/{job_id}",
        board=JobBoard.OTHER,
        ats_type=ATSType.UNKNOWN,
        discovered_at=datetime.utcnow(),
    )


@pytest.mark.asyncio
async def test_backfill_auto_approve_retries_retryable_failures(monkeypatch):
    async def fake_validate(scored_jobs, session_id=""):
        return scored_jobs

    monkeypatch.setattr("backend.orchestrator.pipeline.graph._validate_job_urls", fake_validate)

    state = {
        "session_id": "sess-1",
        "preferences": {"_autopilot_auto_approve": True},
        "backfill_rounds": 1,
        "session_config": {"max_jobs": 10, "minimum_submitted_applications": 10},
        "scored_jobs": [
            ScoredJob(job=_job("new-job", company="FreshCo"), score=95),
            ScoredJob(job=_job("retry-job", company="RetryCo"), score=90),
        ],
        "applications_submitted": [
            ApplicationResult(job_id="done-1", status=ApplicationStatus.SUBMITTED),
            ApplicationResult(job_id="done-2", status=ApplicationStatus.SUBMITTED),
        ],
        "applications_failed": [
            ApplicationResult(
                job_id="retry-job",
                status=ApplicationStatus.FAILED,
                error_category=ApplicationErrorCategory.TIMEOUT,
            )
        ],
        "applications_skipped": [],
        "application_retry_counts": {},
    }

    result = await auto_approve_gate(state)

    assert result["application_queue"] == ["new-job", "retry-job"]
    assert result["active_retry_job_ids"] == ["retry-job"]
    assert result["application_retry_counts"]["retry-job"] == 1


def test_route_after_qa_uses_submitted_target_not_attempted_count():
    state = {
        "session_config": {"max_jobs": 10, "minimum_submitted_applications": 10},
        "applications_submitted": [
            ApplicationResult(job_id="s1", status=ApplicationStatus.SUBMITTED),
            ApplicationResult(job_id="s2", status=ApplicationStatus.SUBMITTED),
        ],
        "applications_failed": [
            ApplicationResult(job_id=f"f{i}", status=ApplicationStatus.FAILED)
            for i in range(8)
        ],
        "applications_skipped": [],
        "backfill_rounds": 0,
    }

    assert route_after_qa(state) == "backfill_prep"
