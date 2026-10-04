"""A completed empty shortlist is a known outcome, not a new model task."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.orchestrator.agents import reporting
from backend.shared.config import settings
from backend.shared.models.schemas import JobListing, JobBoard, SearchConfig


@pytest.fixture
def offline_report(monkeypatch):
    monkeypatch.setattr(reporting, 'emit_agent_event', AsyncMock())
    monkeypatch.setattr('backend.shared.outcome_store.record_outcome', MagicMock())
    monkeypatch.setattr('backend.shared.outcome_store.get_outcome_count', lambda: 0)
    monkeypatch.setattr('backend.optimization.application_feedback.refresh_all_strategies', lambda: None)
    monkeypatch.setattr(settings, 'INDEED_ONLY', True)
    monkeypatch.setattr(settings, 'INDEED_EASY_APPLY_ONLY', True)


@pytest.mark.asyncio
@pytest.mark.parametrize('as_dict', [False, True])
@pytest.mark.parametrize('indeed_only', [False, True])
async def test_completed_scoring_with_two_rejected_jobs_uses_actual_criteria_without_model(offline_report, monkeypatch, as_dict, indeed_only):
    monkeypatch.setattr(settings, 'INDEED_ONLY', indeed_only)
    factory = MagicMock(side_effect=AssertionError('No paid report for an empty shortlist'))
    monkeypatch.setattr(reporting, '_build_llm', factory)
    config = SearchConfig(keywords=['AI Engineer'], locations=['San Francisco'],
                          work_arrangements=['remote', 'hybrid'], salary_min=220000,
                          allow_unpublished_salary=True)
    jobs = [JobListing(id=str(i), title='AI Engineer', company='Example', location='San Francisco',
                       url='https://www.indeed.com/viewjob?jk=fixture', board=JobBoard.INDEED,
                       salary_range='$120,000 - $180,000') for i in range(2)]
    result = await reporting.run_reporting_agent({
        'session_id':'fixture', 'discovered_jobs':jobs, 'scored_jobs':[],
        'agent_statuses':{'scoring':'done'}, 'search_config':config.model_dump() if as_dict else config,
    })
    factory.assert_not_called()
    summary = result['session_summary']
    assert result['status'] == 'completed'
    assert (summary.total_discovered, summary.total_scored, summary.total_applied) == (2, 0, 0)
    text = ' '.join(summary.next_steps)
    assert 'Scoring is complete' in text
    assert '$220,000' in text and 'unpublished' in text
    assert 'San Francisco' in text and 'remote' in text and 'hybrid' in text
    assert 'Indeed Easy Apply' in text
    assert 'receipt' not in text.lower() and 'once scoring' not in text.lower()
    assert not result['errors']


@pytest.mark.asyncio
@pytest.mark.parametrize('next_steps_fail', [False, True])
async def test_no_attempt_context_never_directs_receipt_reconciliation(offline_report, monkeypatch, next_steps_fail):
    monkeypatch.setattr(reporting, '_build_llm', MagicMock())
    invoke = AsyncMock(side_effect=RuntimeError('offline') if next_steps_fail else None,
                       return_value=reporting.NextStepsResult(next_steps=['Review your search criteria.']))
    monkeypatch.setattr(reporting, 'invoke_with_retry', invoke)
    result = await reporting.run_reporting_agent({'session_id':'fixture', 'agent_statuses':{'scoring':'failed'}})
    steps = ' '.join(result['session_summary'].next_steps).lower()
    assert 'receipt' not in steps and 'follow up' not in steps
    assert 'scoring is complete' not in steps
    context = invoke.await_args.args[1][1].content
    assert 'Scoring status: failed' in context
    assert 'Applications attempted: 0' in context
    assert 'reconcile Indeed receipts' not in context
