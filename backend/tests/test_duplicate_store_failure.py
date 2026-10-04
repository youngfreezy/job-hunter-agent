from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

import pytest

from backend.shared import application_store


def test_duplicate_lookup_failure_cannot_mean_no_prior_submission(monkeypatch):
    monkeypatch.setattr(application_store, '_connect', MagicMock(side_effect=RuntimeError('database unavailable')))
    with pytest.raises(RuntimeError, match='verify prior applications'):
        application_store.check_already_applied('job', user_id='user')


@pytest.mark.asyncio
async def test_duplicate_lookup_outage_stops_before_browser_or_paid_supervisor(monkeypatch):
    from backend.orchestrator.agents import application
    from backend.shared.models.schemas import ApplicationStatus, JobListing, JobBoard
    from backend.shared import llm
    from backend.shared.config import settings

    monkeypatch.setattr(settings, 'INDEED_ONLY', True)
    monkeypatch.setattr(application, '_board_login_available', lambda *_: True)
    monkeypatch.setattr(application, 'check_sufficient_credits', lambda *_: True)
    monkeypatch.setattr(application_store, '_connect', MagicMock(side_effect=RuntimeError('database unavailable')))
    monkeypatch.setattr(application, '_db_record_result', MagicMock())
    monkeypatch.setattr(application, 'emit_agent_event', AsyncMock())
    paid = MagicMock(side_effect=AssertionError('Must not call a model'))
    monkeypatch.setattr(llm, 'build_llm', paid)
    context = SimpleNamespace(new_page=AsyncMock(), pages=[])
    job = JobListing(id='job', title='Engineer', company='Example', location='Remote',
                     url='https://www.indeed.com/viewjob?jk=job', board=JobBoard.INDEED)
    result = await application._apply_to_job('job', job,
        {'user_id': 'user', 'session_config': {'discovery_mode': 'manual_urls'}}, 'session', context=context)
    assert result.status == ApplicationStatus.FAILED
    assert result.failure_step == 'duplicate_check'
    context.new_page.assert_not_awaited()
    decision = await application._call_application_supervisor(result, [result], 1, True, 'session')
    assert decision.decision == application.SupervisorDecision.PAUSE
    paid.assert_not_called()
