from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from backend.browser.application_routing import is_public_application_url, ordered_pending_jobs

@pytest.mark.parametrize('url,allowed', [
    ('https://jobs.lever.co/acme/job', True),
    ('https://careers.example.com/apply', True),
    ('http://careers.example.com/apply', False),
    ('https://localhost/apply', False),
    ('https://127.0.0.1/apply', False),
    ('https://169.254.169.254/latest/meta-data', False),
    ('https://[::1]/apply', False),
    ('https://internal.local/apply', False),
    ('https://user:secret@careers.example.com/apply', False),
    ('https://careers.example.com:8000/apply', False),
])
def test_application_destination_boundary(url, allowed):
    assert is_public_application_url(url) is allowed


def test_native_queue_drains_before_external_queue_without_duplicates():
    routes = {'one': {'url': 'https://jobs.lever.co/acme/one'}}
    assert ordered_pending_jobs(['one', 'two', 'three', 'two'], {'three'}, routes) == ['two', 'one']

@pytest.mark.asyncio
async def test_employer_handoff_is_queued_then_executed_without_counting_as_submission(monkeypatch):
    from unittest.mock import MagicMock
    from backend.orchestrator.agents import application
    from backend.orchestrator.pipeline import graph
    from backend.shared.config import settings
    from backend.shared.models.schemas import ApplicationResult, ApplicationStatus, JobListing, JobBoard
    monkeypatch.setattr(settings, 'INDEED_ONLY', True)
    monkeypatch.setattr(settings, 'INDEED_EASY_APPLY_ONLY', False)
    monkeypatch.setattr(application, 'emit_agent_event', AsyncMock())
    manager = MagicMock(stagehand=object(), live_view_url=None)
    manager.start_for_task = AsyncMock()
    manager.new_context = AsyncMock(return_value=('ctx', object()))
    manager.stop = AsyncMock()
    monkeypatch.setattr(application, 'BrowserManager', lambda: manager)
    job = JobListing(id='one', title='Engineer', company='Acme', location='Remote',
                     url='https://www.indeed.com/viewjob?jk=one', board=JobBoard.INDEED)
    apply = AsyncMock(side_effect=[
        ApplicationResult(job_id='one', status=ApplicationStatus.QUEUED, external_application_url='https://jobs.lever.co/acme/one'),
        ApplicationResult(job_id='one', status=ApplicationStatus.SUBMITTED),
    ])
    monkeypatch.setattr(application, '_apply_to_job', apply)
    state = {'session_id':'session', 'application_queue':['one'], 'discovered_jobs':[job]}
    routed = await application.run_application_agent(state)
    assert routed['applications_submitted'] == routed['applications_failed'] == routed['applications_skipped'] == []
    assert routed['employer_application_queue']['one']['source_url'] == job.url
    state.update(routed)
    assert graph.route_after_application(state) == 'application'
    result = await application.run_application_agent(state)
    assert len(result['applications_submitted']) == 1
    assert apply.await_args.kwargs['employer_url'] == 'https://jobs.lever.co/acme/one'
    assert manager.start_for_task.await_args.kwargs['purpose'] == 'apply_external'

@pytest.mark.asyncio
async def test_native_redirect_queues_before_any_applicant_action(monkeypatch):
    from backend.shared.config import settings
    monkeypatch.setattr(settings, 'INDEED_EASY_APPLY_ONLY', False)
    from unittest.mock import MagicMock
    from backend.browser.tools.appliers.indeed import IndeedApplier
    from backend.shared.models.schemas import JobListing, JobBoard, ApplicationStatus
    page=SimpleNamespace(context=SimpleNamespace(_jobhunter_external_redirect='https://jobs.lever.co/acme/one'))
    agent=MagicMock(metrics=AsyncMock())
    agent.extract=AsyncMock(); agent.act=AsyncMock()
    job=JobListing(id='one',title='Engineer',company='Acme',location='Remote',url='https://www.indeed.com/viewjob?jk=one',board=JobBoard.INDEED)
    result=await IndeedApplier(page,'session',stagehand=agent).run(job=job,user_profile={},resume_text='',cover_letter='')
    assert result.status == ApplicationStatus.QUEUED
    assert result.external_application_url == 'https://jobs.lever.co/acme/one'
    agent.extract.assert_not_awaited()
    agent.act.assert_not_awaited()

@pytest.mark.asyncio
@pytest.mark.parametrize('addresses,expected', [(['93.184.215.14'],True), (['127.0.0.1'],False), (['93.184.215.14','10.0.0.1'],False), ([],False)])
async def test_dns_destination_cannot_resolve_to_private_addresses(monkeypatch, addresses, expected):
    import asyncio
    from backend.browser.application_routing import resolves_publicly
    monkeypatch.setattr(asyncio.get_running_loop(), 'getaddrinfo', AsyncMock(
        return_value=[(None,None,None,None,(addr,443)) for addr in addresses]))
    assert await resolves_publicly('https://careers.example.com/apply') is expected
