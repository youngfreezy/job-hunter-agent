# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Tests for Quick Apply (discovery_mode=manual_urls).

Quick Apply sessions should bypass ALL filtering and scoring:
1. No LLM scoring — all jobs get score=100
2. No job deduplication (same company/title allowed)
3. No cross-session duplicate check
4. No company rate limit check
5. No per-session company dedup
6. No shortlist review — auto-approved straight to application
7. No backfill loop after QA
"""

import uuid
from datetime import datetime

import pytest

from backend.orchestrator.agents.scoring import run_scoring_agent
from backend.orchestrator.pipeline.graph import (
    auto_approve_gate,
    _route_after_auto_approve_gate,
    route_after_qa,
)
from backend.shared.models.schemas import (
    ATSType,
    JobBoard,
    JobListing,
    ScoredJob,
)


def _job(job_id: str = "", title: str = "Engineer", company: str = "Acme") -> JobListing:
    return JobListing(
        id=job_id or uuid.uuid4().hex[:12],
        title=title,
        company=company,
        location="Remote",
        url=f"https://example.com/{uuid.uuid4().hex[:8]}",
        board=JobBoard.OTHER,
        ats_type=ATSType.UNKNOWN,
        discovered_at=datetime.utcnow(),
    )


def _quick_apply_state(**overrides) -> dict:
    """Build a minimal Quick Apply state dict."""
    state = {
        "session_id": f"qa-test-{uuid.uuid4().hex[:8]}",
        "resume_text": "Senior software engineer with 10 years experience",
        "session_config": {"discovery_mode": "manual_urls", "job_urls": []},
        "discovered_jobs": [],
        "scored_jobs": [],
        "keywords": ["software engineer"],
        "preferences": {},
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# 1. Scoring: skip LLM, assign score=100
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quick_apply_skips_llm_scoring(monkeypatch):
    """Quick Apply should NOT call the LLM — all jobs get score=100."""
    llm_called = False

    async def fake_invoke(*_args, **_kwargs):
        nonlocal llm_called
        llm_called = True
        raise AssertionError("LLM should not be called for Quick Apply")

    async def fake_emit(*_args, **_kwargs):
        return None

    monkeypatch.setattr("backend.orchestrator.agents.scoring.build_llm", lambda **_: type("FakeLLM", (), {"with_structured_output": lambda self, _: self})())
    monkeypatch.setattr("backend.orchestrator.agents.scoring.invoke_with_retry", fake_invoke)
    monkeypatch.setattr("backend.orchestrator.agents.scoring.emit_agent_event", fake_emit)
    monkeypatch.setattr("backend.orchestrator.agents.scoring.get_active_prompt", lambda _key: None)

    jobs = [_job(title="Backend Engineer"), _job(title="Frontend Engineer")]
    state = _quick_apply_state(discovered_jobs=jobs)

    result = await run_scoring_agent(state)

    assert not llm_called, "LLM was called but should be skipped for Quick Apply"
    assert result["status"] == "tailoring"
    assert len(result["scored_jobs"]) == 2
    for sj in result["scored_jobs"]:
        assert sj.score == 100


# ---------------------------------------------------------------------------
# 2. Scoring: no dedup (same company/title kept)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quick_apply_keeps_duplicate_titles(monkeypatch):
    """Two jobs with identical company='Unknown' and title='' should NOT be deduped."""
    async def fake_emit(*_args, **_kwargs):
        return None

    monkeypatch.setattr("backend.orchestrator.agents.scoring.emit_agent_event", fake_emit)
    monkeypatch.setattr("backend.orchestrator.agents.scoring.get_active_prompt", lambda _key: None)

    # Simulate two Workday jobs that hydrate identically
    jobs = [
        _job(title="Unknown Position", company="Unknown"),
        _job(title="Unknown Position", company="Unknown"),
    ]
    state = _quick_apply_state(discovered_jobs=jobs)

    result = await run_scoring_agent(state)

    assert len(result["scored_jobs"]) == 2, "Both jobs should survive — dedup must be skipped"


# ---------------------------------------------------------------------------
# 3. Auto-approve gate: Quick Apply skips shortlist review
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quick_apply_auto_approves(monkeypatch):
    """Quick Apply should auto-approve all jobs (skip shortlist review)."""
    async def fake_validate(scored_jobs, session_id=""):
        return scored_jobs

    monkeypatch.setattr("backend.orchestrator.pipeline.graph._validate_job_urls", fake_validate)

    jobs = [ScoredJob(job=_job(), score=100) for _ in range(3)]
    state = _quick_apply_state(scored_jobs=jobs)

    result = await auto_approve_gate(state)

    assert "application_queue" in result
    assert len(result["application_queue"]) == 3


def test_quick_apply_routes_past_shortlist_review():
    """Quick Apply should route to supervise_after_shortlist, NOT shortlist_review."""
    state = _quick_apply_state(
        application_queue=["job1", "job2"],
    )

    route = _route_after_auto_approve_gate(state)

    assert route == "supervise_after_shortlist", f"Expected supervise_after_shortlist, got {route}"


# ---------------------------------------------------------------------------
# 4. QA routing: no backfill for Quick Apply
# ---------------------------------------------------------------------------


def test_quick_apply_skips_backfill():
    """After QA, Quick Apply should go to reporting — NOT backfill."""
    state = _quick_apply_state(
        applications_submitted=[],
        applications_failed=[],
        applications_skipped=[],
    )

    route = route_after_qa(state)

    assert route == "reporting", f"Expected reporting, got {route}"


# ---------------------------------------------------------------------------
# 5. Normal sessions still get LLM scoring (sanity check)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normal_session_uses_llm_scoring(monkeypatch):
    """Non-Quick-Apply sessions MUST call the LLM for scoring."""
    from backend.orchestrator.agents.scoring import ScoringBatchResult

    llm_called = False

    async def fake_invoke(_llm, messages, **_kwargs):
        nonlocal llm_called
        llm_called = True
        prompt = messages[-1].content
        ids = []
        for line in prompt.splitlines():
            if line.startswith("- ID: "):
                ids.append(line.replace("- ID: ", "").strip())
        return ScoringBatchResult(
            scores=[{"job_id": jid, "score": 75, "score_breakdown": {}, "reasons": ["ok"]} for jid in ids]
        )

    async def fake_emit(*_args, **_kwargs):
        return None

    monkeypatch.setattr("backend.orchestrator.agents.scoring.build_llm", lambda **_: type("FakeLLM", (), {"with_structured_output": lambda self, _: self})())
    monkeypatch.setattr("backend.orchestrator.agents.scoring.invoke_with_retry", fake_invoke)
    monkeypatch.setattr("backend.orchestrator.agents.scoring.emit_agent_event", fake_emit)
    monkeypatch.setattr("backend.orchestrator.agents.scoring.get_active_prompt", lambda _key: None)

    jobs = [_job(title="Backend Engineer", company="TestCo")]
    state = {
        "session_id": "normal-test",
        "resume_text": "Senior software engineer",
        "discovered_jobs": jobs,
        "keywords": ["software engineer"],
        # No session_config → normal session
    }

    await run_scoring_agent(state)

    assert llm_called, "Normal sessions must use LLM scoring"
