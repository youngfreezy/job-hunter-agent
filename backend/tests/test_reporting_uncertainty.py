from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.orchestrator.agents import reporting
from backend.shared.models.schemas import ApplicationResult, ApplicationStatus, ApplicationErrorCategory


@pytest.mark.asyncio
@pytest.mark.parametrize('next_steps_fail', [False, True])
async def test_reporting_separates_uncertain_delivery_and_requires_reconciliation(monkeypatch, next_steps_fail):
    monkeypatch.setattr(reporting, 'emit_agent_event', AsyncMock())
    monkeypatch.setattr(reporting, '_build_llm', MagicMock())
    invoke = AsyncMock(side_effect=RuntimeError('offline') if next_steps_fail else None,
                       return_value=reporting.NextStepsResult(next_steps=['Review results.']))
    monkeypatch.setattr(reporting, 'invoke_with_retry', invoke)
    record = MagicMock()
    monkeypatch.setattr('backend.shared.outcome_store.record_outcome', record)
    monkeypatch.setattr('backend.shared.outcome_store.get_outcome_count', lambda: 0)
    monkeypatch.setattr('backend.optimization.application_feedback.refresh_all_strategies', lambda: None)
    failed = [ApplicationResult(job_id='uncertain', status=ApplicationStatus.FAILED,
                  error_category=ApplicationErrorCategory.SUBMISSION_UNCERTAIN),
              ApplicationResult(job_id='failed', status=ApplicationStatus.FAILED,
                  error_category=ApplicationErrorCategory.FORM_NAVIGATION)]
    result = await reporting.run_reporting_agent({'session_id':'fixture', 'applications_failed':failed})
    summary = result['session_summary']
    assert summary.total_applied == 0
    assert summary.total_failed == 1
    assert summary.total_uncertain == 1
    assert 'before retrying' in summary.next_steps[0].lower()
    assert 'receipt' in summary.next_steps[0].lower()
    assert record.call_args.args[1]['error_categories']['submission_uncertain'] == 1
    assert record.call_args.args[1]['ats_breakdown']['unknown']['uncertain'] == 1
    assert record.call_args.args[1]['failed_count'] == 1
    assert failed[0].error_category == ApplicationErrorCategory.SUBMISSION_UNCERTAIN
    prompt = invoke.call_args.args[1][1].content
    assert 'unverified: 1' in prompt
