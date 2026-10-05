"""Verification summarizes adapter evidence without paying a model to count."""

from unittest.mock import AsyncMock, Mock

import pytest

from backend.orchestrator.agents import verification
from backend.shared.models.schemas import ApplicationResult, ApplicationStatus


@pytest.mark.asyncio
async def test_verification_counts_confirmed_statuses_without_model_inference(monkeypatch):
    model = Mock(side_effect=AssertionError("Verification must not call a model"))
    monkeypatch.setattr(verification, "_build_llm", model, raising=False)
    events = AsyncMock()
    monkeypatch.setattr(verification, "emit_agent_event", events)
    submitted = ApplicationResult(job_id="confirmed", status=ApplicationStatus.SUBMITTED)
    uncertain = ApplicationResult(job_id="uncertain", status=ApplicationStatus.FAILED)
    result = await verification.run_verification_agent({
        "session_id": "test", "applications_submitted": [submitted, uncertain],
    })

    assert result["errors"] == []
    assert "1 verified, 1 failed" in result["agent_statuses"]["verification"]
    assert events.await_args.args[2]["step"] == "Done — 1 confirmed, 1 need attention"
    model.assert_not_called()
    assert uncertain.status is ApplicationStatus.FAILED


@pytest.mark.asyncio
async def test_verification_of_empty_results_uses_no_external_services(monkeypatch):
    events = AsyncMock()
    monkeypatch.setattr(verification, "emit_agent_event", events)
    assert await verification.run_verification_agent({}) == {
        "agent_statuses": {"verification": "completed -- no applications to verify"},
        "errors": [],
    }
    events.assert_not_called()
