from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.orchestrator.agents import application, qa
from backend.orchestrator.pipeline import graph
from backend.shared.models.schemas import ApplicationErrorCategory, ApplicationResult, ApplicationStatus, JobBoard, JobListing


def _pending_state(count=5):
    return {
        'session_id': 'session', 'applications_skipped': [f'j{i}' for i in range(count)],
        'application_questions': {f'j{i}': {'question': 'Do you hold this certification?'} for i in range(count)},
        'session_config': {'max_jobs': 20, 'minimum_submitted_applications': 20},
    }


@pytest.mark.asyncio
async def test_pending_answers_do_not_halt_backfill_or_call_qa_model(monkeypatch):
    model = MagicMock(side_effect=AssertionError('No model needed for pending answers'))
    monkeypatch.setattr(qa, '_build_llm', model)
    monkeypatch.setattr(qa, 'emit_agent_event', AsyncMock())
    state = _pending_state()
    result = await qa.run_qa_agent(state)
    assert result['qa_analysis']['decision'] == 'continue'
    assert result['errors'] == []
    model.assert_not_called()
    state.update(result)
    assert graph.route_after_qa(state) == 'backfill_prep'


def test_pending_answers_do_not_inflate_automation_failure_statistics():
    state = _pending_state(4)
    state['applications_failed'] = [ApplicationResult(job_id='failed', status=ApplicationStatus.FAILED)]
    summary = qa._summarise_results(state)
    assert summary['pending_answers'] == 4
    assert summary['total_attempts'] == 1
    assert summary['skipped'] == 0
    assert summary['failed'] == 1


def test_real_failures_still_count_when_questions_are_pending():
    state = _pending_state()
    state['applications_failed'] = [ApplicationResult(job_id=f'f{i}', status=ApplicationStatus.FAILED) for i in range(5)]
    assert qa._summarise_results(state)['total_attempts'] == 5


@pytest.mark.asyncio
async def test_unknown_answer_queues_one_job_and_next_job_can_submit(monkeypatch):
    from backend.shared.config import settings
    monkeypatch.setattr(settings, 'INDEED_ONLY', True)
    monkeypatch.setattr(application, 'emit_agent_event', AsyncMock())
    supervisor = AsyncMock(side_effect=AssertionError('Pending answers must bypass failure supervisor'))
    monkeypatch.setattr(application, '_call_application_supervisor', supervisor)
    manager = MagicMock(stagehand=object(), live_view_url=None, browserbase_session_id=None)
    manager.start_for_task = AsyncMock()
    manager.new_context = AsyncMock(return_value=('ctx', object()))
    manager.stop = AsyncMock()
    monkeypatch.setattr(application, 'BrowserManager', lambda: manager)
    jobs = [JobListing(id=key, title='Engineer', company=key, location='Remote',
                      url=f'https://www.indeed.com/viewjob?jk={key}', board=JobBoard.INDEED)
            for key in ('unknown', 'ready')]
    apply = AsyncMock(side_effect=[
        ApplicationResult(job_id='unknown', status=ApplicationStatus.SKIPPED,
                          error_category=ApplicationErrorCategory.NEEDS_INPUT,
                          error_message='Do you hold this certification?'),
        ApplicationResult(job_id='ready', status=ApplicationStatus.SUBMITTED),
    ])
    monkeypatch.setattr(application, '_apply_to_job', apply)
    state = {'session_id': 'session', 'application_queue': ['unknown', 'ready'],
             'discovered_jobs': jobs, 'consecutive_failures': 2}
    first = await application.run_application_agent(state)
    assert first['application_questions']['unknown']['question'] == 'Do you hold this certification?'
    assert first['status'] == 'applying'
    assert first['consecutive_failures'] == 0
    state.update(first)
    assert graph.route_after_application(state) == 'application'
    second = await application.run_application_agent(state)
    assert second['applications_submitted'][0].job_id == 'ready'
    assert second['application_questions'] == first['application_questions']
    assert apply.await_args.kwargs['job_id'] == 'ready'
    supervisor.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_systemic_failure_halt_is_preserved_with_pending_answers(monkeypatch):
    state = _pending_state()
    state['applications_failed'] = [ApplicationResult(job_id=f'f{i}', status=ApplicationStatus.FAILED) for i in range(5)]
    monkeypatch.setattr(qa, '_build_llm', MagicMock())
    monkeypatch.setattr(qa, 'emit_agent_event', AsyncMock())
    monkeypatch.setattr(qa, 'invoke_with_retry', AsyncMock(return_value=qa.QADecision(
        decision='halt', reasoning='Five actual automation failures.')))
    assert (await qa.run_qa_agent(state))['qa_analysis']['decision'] == 'halt'


def test_stale_question_does_not_hide_real_result():
    state = _pending_state(1)
    state['applications_failed'] = [ApplicationResult(job_id='j0', status=ApplicationStatus.FAILED)]
    summary = qa._summarise_results(state)
    assert summary['pending_answers'] == 0
    assert summary['failed'] == 1

@pytest.mark.asyncio
@pytest.mark.parametrize('remaining_jobs', [False, True])
@pytest.mark.parametrize('failure_step', ['model_budget', 'duplicate_check'])
async def test_safety_stop_reaches_pause_gate_without_paid_followup(monkeypatch, remaining_jobs, failure_step):
    from backend.shared.config import settings
    from backend.browser.stagehand_budget import CEILING_STOP
    monkeypatch.setattr(settings, 'INDEED_ONLY', True)
    monkeypatch.setattr(application, 'emit_agent_event', AsyncMock())
    manager = MagicMock(stagehand=object(), live_view_url=None, browserbase_session_id=None)
    manager.start_for_task = AsyncMock()
    manager.new_context = AsyncMock(return_value=('ctx', object()))
    manager.stop = AsyncMock()
    monkeypatch.setattr(application, 'BrowserManager', lambda: manager)
    jobs = [JobListing(id=key, title='Engineer', company=key, location='Remote',
                       url=f'https://www.indeed.com/viewjob?jk={key}', board=JobBoard.INDEED)
            for key in (('blocked', 'next') if remaining_jobs else ('blocked',))]
    apply = AsyncMock(return_value=ApplicationResult(
        job_id='blocked', status=ApplicationStatus.FAILED,
        error_message=CEILING_STOP, failure_step=failure_step))
    monkeypatch.setattr(application, '_apply_to_job', apply)
    build = MagicMock(side_effect=AssertionError('Must not call a paid supervisor'))
    monkeypatch.setattr('backend.shared.llm.build_llm', build)
    state = {'session_id': 'session', 'application_queue': [job.id for job in jobs],
             'discovered_jobs': jobs, 'preferences': {'_skip_coach_review': True},
             'human_messages': ['What happened?'], 'steering_messages_processed': 0}
    updates = await application.run_application_agent(state)
    state.update(updates)
    assert state['pause_requested'] is True
    if failure_step == 'model_budget':
        assert state['pending_supervisor_response'] == CEILING_STOP
    else:
        assert 'Restore storage' in state['pending_supervisor_response']
    assert state['pause_resume_node'] == 'application'
    steering = AsyncMock(side_effect=AssertionError('No paid steering adjudication'))
    monkeypatch.setattr(graph.workflow_supervisor, 'run_workflow_supervisor', steering)
    node = graph.make_workflow_supervisor_node(graph._continue_after_application)
    assert await node(state) == {}
    assert graph.route_after_supervise_after_application(state) == 'pause_gate'
    apply.assert_awaited_once()
    build.assert_not_called()
    steering.assert_not_awaited()
    manager.stop.assert_awaited_once()
