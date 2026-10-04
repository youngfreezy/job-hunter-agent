"""Demo restriction must reject employer work before paid browser actions."""
from unittest.mock import AsyncMock, MagicMock
import pytest

from backend.shared.config import settings
from backend.shared.models.schemas import ApplicationStatus, SearchConfig
from backend.browser.tools.appliers.indeed import IndeedApplier
from backend.browser.tools.job_boards.indeed import matches_search
from backend.orchestrator.agents import application
from backend.tests.test_indeed_applier import _job, _page, _stagehand


@pytest.fixture(autouse=True)
def easy_only(monkeypatch):
    monkeypatch.setattr(settings, 'INDEED_EASY_APPLY_ONLY', True)
    monkeypatch.setattr('backend.browser.tools.appliers.base.emit_agent_event', AsyncMock())


def test_discovery_requires_easy_apply_metadata_and_legacy_opt_out(monkeypatch):
    job = _job()
    assert matches_search(job, SearchConfig(keywords=['Engineer'], locations=['Austin']))
    job.is_easy_apply = False
    assert not matches_search(job, SearchConfig(keywords=['Engineer'], locations=['Austin']))
    monkeypatch.setattr(settings, 'INDEED_EASY_APPLY_ONLY', False)
    assert matches_search(job, SearchConfig(keywords=['Engineer'], locations=['Austin']))


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['external', 'auth'])
async def test_observed_employer_or_login_skips_without_action(kind):
    page = _page()
    page.context._jobhunter_external_redirect = None
    agent = _stagehand(page, [dict(kind=kind, instruction='Click Apply on company website', reason='Employer login required')])
    result = await IndeedApplier(page, 's', stagehand=agent).run(
        job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert result.status == ApplicationStatus.SKIPPED
    assert 'Indeed Easy Apply only' in result.error_message
    assert result.external_application_url is None
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('captured', [False, True])
async def test_redirect_skips_before_any_model_call(captured):
    page = _page('https://jobs.example.com/apply')
    page.context._jobhunter_external_redirect = page.url if captured else None
    agent = _stagehand(page, [])
    result = await IndeedApplier(page, 's', stagehand=agent).run(
        job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert result.status == ApplicationStatus.SKIPPED
    assert result.external_application_url is None
    agent.extract.assert_not_awaited()
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
async def test_preexisting_employer_queue_is_durably_skipped_before_browser(monkeypatch):
    job = _job()
    manager = MagicMock()
    monkeypatch.setattr(application, 'BrowserManager', manager)
    record = MagicMock()
    monkeypatch.setattr(application, '_db_record_result', record)
    monkeypatch.setattr(application, 'emit_agent_event', AsyncMock())
    result = await application.run_application_agent({
        'session_id': 's', 'application_queue': [job.id], 'discovered_jobs': [job],
        'employer_application_queue': {job.id: {'url': 'https://jobs.example.com/apply', 'status': 'queued'}},
    })
    assert result['applications_submitted'] == result['applications_failed'] == []
    assert result['applications_skipped'] == [job.id]
    assert result['employer_application_queue'][job.id]['status'] == 'skipped'
    assert 'Indeed Easy Apply only' in record.call_args.kwargs['error_message']
    assert record.call_args.kwargs['status'] == 'skipped'
    manager.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('source,current,employer', [
    ('https://www.indeed.com/viewjob?jk=one', 'https://boards.greenhouse.io/acme/one', False),
    ('https://jobs.lever.co/acme/one', 'https://jobs.lever.co/acme/one', False),
    ('https://www.indeed.com/viewjob?jk=one', 'https://www.indeed.com/viewjob?jk=one', True),
])
async def test_dispatcher_rejects_external_paths_before_detection(monkeypatch, source, current, employer):
    from backend.browser.tools.appliers import dispatcher
    detect = MagicMock()
    monkeypatch.setattr(dispatcher, 'detect_ats_from_url', detect)
    result = await dispatcher.apply_with_playwright(
        job=_job(source), user_profile={}, resume_text='', cover_letter='',
        resume_file_path=None, session_id='s', page=_page(current), employer_site=employer)
    assert result.status == ApplicationStatus.SKIPPED
    detect.assert_not_called()


@pytest.mark.asyncio
async def test_non_indeed_candidate_skips_before_api_or_browser_when_legacy_discovery_enabled(monkeypatch):
    from backend.shared.models.schemas import ATSType
    monkeypatch.setattr(settings, 'INDEED_ONLY', False)
    job = _job('https://boards.greenhouse.io/acme/one')
    job.ats_type = ATSType.GREENHOUSE
    manager = MagicMock()
    apply = AsyncMock()
    monkeypatch.setattr(application, 'BrowserManager', manager)
    monkeypatch.setattr(application, '_apply_to_job', apply)
    monkeypatch.setattr(application, '_db_record_result', MagicMock())
    monkeypatch.setattr(application, 'emit_agent_event', AsyncMock())
    result = await application.run_application_agent({
        'session_id': 's', 'application_queue': [job.id], 'discovered_jobs': [job]})
    assert result['applications_skipped'] == [job.id]
    assert result['applications_submitted'] == []
    manager.assert_not_called()
    apply.assert_not_awaited()


def test_redirect_after_submit_retains_uncertain_hold():
    from backend.shared.models.schemas import ApplicationErrorCategory
    page = _page()
    page.context._jobhunter_external_redirect = 'https://jobs.example.com/apply'
    applier = IndeedApplier(page, 's')
    applier._submission_attempted = True
    result = applier._external_route('one')
    assert result.status == ApplicationStatus.FAILED
    assert result.error_category == ApplicationErrorCategory.SUBMISSION_UNCERTAIN


@pytest.mark.asyncio
async def test_captured_redirect_skips_before_cover_letter_and_persists_reason(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(settings, 'INDEED_ONLY', True)
    monkeypatch.setattr(settings, 'BROWSER_MODE', 'browserbase')
    monkeypatch.setattr(application, '_board_login_available', lambda *_: True)
    monkeypatch.setattr(application, 'check_already_applied', lambda *a, **kw: None)
    monkeypatch.setattr(application, 'check_company_rate_limit', lambda *a, **kw: None)
    record = MagicMock()
    monkeypatch.setattr(application, '_db_record_result', record)
    monkeypatch.setattr(application, 'emit_agent_event', AsyncMock())
    monkeypatch.setattr(application.asyncio, 'sleep', AsyncMock())
    page = SimpleNamespace(goto=AsyncMock(), url=_job().url, is_closed=lambda: False,
                           close=AsyncMock(), wait_for_function=AsyncMock())
    context = SimpleNamespace(pages=[page], _jobhunter_external_redirect='https://careers.example.com/apply')
    result = await application._apply_to_job(_job().id, _job(), {}, 's', context=context)
    assert result.status == ApplicationStatus.SKIPPED
    assert record.call_args.kwargs['status'] == 'skipped'
    assert 'Indeed Easy Apply only' in record.call_args.kwargs['error_message']
    page.wait_for_function.assert_not_awaited()
