from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.orchestrator.agents import application
from backend.orchestrator.pipeline import graph
from backend.shared.config import settings
from backend.shared.models.schemas import ApplicationResult, ApplicationStatus, JobListing, JobBoard


def listing(job_id):
    return JobListing(id=job_id, title='Engineer', company=job_id, location='Remote',
                      url=f'https://www.indeed.com/viewjob?jk={job_id}', board=JobBoard.INDEED)


@pytest.mark.asyncio
@pytest.mark.parametrize('body,expired', [
    ('loading', False),
    ('additional verification required. ray id: a4404ffeb', False),
    ('senior engineer, job reference 404123. apply now', False),
    ('this job has expired', True),
])
async def test_indeed_expiry_requires_an_explicit_listing_message(monkeypatch, body, expired):
    monkeypatch.setattr(settings, 'INDEED_ONLY', True)
    page = SimpleNamespace(url=listing('one').url, evaluate=AsyncMock(return_value=body))
    assert await application._is_dead_page(page) is expired


@pytest.mark.asyncio
async def test_indeed_uses_canonical_profile_and_skips_unused_resume_rewrites(monkeypatch):
    monkeypatch.setattr(settings, 'INDEED_ONLY', True)
    tailor = AsyncMock()
    monkeypatch.setattr(graph.resume_tailor, 'run', tailor)
    monkeypatch.setattr(graph, 'emit_agent_event', AsyncMock())
    state = {'session_id': 'session', 'resume_text': 'Actual Applicant\nactual@example.com',
             'coached_resume': 'Rewritten Applicant\nrewritten@example.com'}
    profile = await application._extract_user_profile(state)
    assert profile['email'] == 'actual@example.com'
    result = await graph.resume_tailor_node(state)
    assert result['status'] == 'applying'
    tailor.assert_not_awaited()


@pytest.mark.asyncio
async def test_materials_only_still_creates_requested_resume_drafts(monkeypatch):
    monkeypatch.setattr(settings, 'INDEED_ONLY', True)
    tailor = AsyncMock(return_value={'tailored_resumes': {}})
    monkeypatch.setattr(graph.resume_tailor, 'run', tailor)
    state = {'session_config': {'application_mode': 'materials_only'}}
    await graph.resume_tailor_node(state)
    tailor.assert_awaited_once_with(state)


@pytest.mark.asyncio
async def test_indeed_application_uses_managed_default_tab_without_local_stealth(monkeypatch):
    monkeypatch.setattr(settings, 'INDEED_ONLY', True)
    monkeypatch.setattr(settings, 'BROWSER_MODE', 'browserbase')
    monkeypatch.setattr(application, '_board_login_available', lambda *_: True)
    monkeypatch.setattr(application, 'check_already_applied', lambda *a, **kw: None)
    monkeypatch.setattr(application, 'check_company_rate_limit', lambda *a, **kw: None)
    monkeypatch.setattr(application, '_db_record_result', MagicMock())
    monkeypatch.setattr(application, 'emit_agent_event', AsyncMock())
    monkeypatch.setattr(application, '_has_captcha', AsyncMock(return_value=False))
    monkeypatch.setattr(application, '_is_dead_page', AsyncMock(return_value=True))
    monkeypatch.setattr(application.asyncio, 'sleep', AsyncMock())
    stealth = AsyncMock()
    monkeypatch.setattr(application, 'apply_stealth', stealth)
    page = SimpleNamespace(goto=AsyncMock(), wait_for_function=AsyncMock(), url=listing('one').url, is_closed=lambda: False, close=AsyncMock())
    context = SimpleNamespace(pages=[page], new_page=AsyncMock(return_value=page))
    result = await application._apply_to_job('one', listing('one'), {}, 'session', context=context)
    assert result.status == ApplicationStatus.SKIPPED
    assert result.error_message == 'job_expired'
    context.new_page.assert_not_awaited()
    stealth.assert_not_awaited()
    page.goto.assert_awaited_once()
    page.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_indeed_batch_processes_only_one_job_on_shared_default_tab(monkeypatch):
    monkeypatch.setattr(settings, 'INDEED_ONLY', True)
    monkeypatch.setattr(settings, 'SKYVERN_CONCURRENCY', 3)
    monkeypatch.setattr(application, 'emit_agent_event', AsyncMock())
    manager = MagicMock()
    manager.start_for_task = AsyncMock()
    manager.new_context = AsyncMock(return_value=('ctx', object()))
    manager.stop = AsyncMock()
    manager.live_view_url = None
    monkeypatch.setattr(application, 'BrowserManager', lambda: manager)
    apply = AsyncMock(side_effect=lambda *args, **kwargs: ApplicationResult(
        job_id=kwargs.get('job_id', args[0] if args else ''), status=ApplicationStatus.SKIPPED,
    ))
    monkeypatch.setattr(application, '_apply_to_job', apply)
    result = await application.run_application_agent({
        'session_id': 'session', 'application_queue': ['one', 'two'],
        'discovered_jobs': [listing('one'), listing('two')],
    })
    assert result['applications_skipped'] == ['one']
    assert apply.await_count == 1
    manager.stop.assert_awaited_once()
