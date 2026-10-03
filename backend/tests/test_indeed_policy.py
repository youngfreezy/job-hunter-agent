import pytest
from backend.browser.indeed_policy import is_indeed_url, enforce_indeed_config
from backend.shared.models.schemas import StartSessionRequest, SessionConfig

@pytest.mark.parametrize('url,allowed', [
 ('https://www.indeed.com/viewjob?jk=123', True),
 ('https://smartapply.indeed.com/form', True),
 ('https://evilindeed.com/job', False),
 ('https://indeed.com.evil.test/job', False),
 ('https://jobs.lever.co/job', False),
 ('http://www.indeed.com/job', False),
])
def test_domain_boundary(url, allowed):
 assert is_indeed_url(url) is allowed

def test_indeed_config_overrides_stale_board_selection():
 request = StartSessionRequest(config=SessionConfig(job_boards=['linkedin']))
 enforce_indeed_config(request)
 assert request.config.job_boards == ['indeed']

def test_manual_external_urls_rejected():
 request = StartSessionRequest(config=SessionConfig(job_urls=['https://jobs.lever.co/job']))
 with pytest.raises(ValueError, match='Indeed'):
  enforce_indeed_config(request)

@pytest.mark.asyncio
async def test_application_cannot_use_external_api_in_indeed_mode(monkeypatch):
 from backend.orchestrator.agents.application import _apply_to_job
 from backend.shared.config import settings
 from backend.shared.models.schemas import JobListing,JobBoard,ATSType,ApplicationStatus
 monkeypatch.setattr(settings,'INDEED_ONLY',True)
 listing=JobListing(id='external',title='Engineer',company='Example',location='Remote',url='https://jobs.lever.co/example',board=JobBoard.INDEED,ats_type=ATSType.LEVER)
 result=await _apply_to_job('external',listing,{},'session')
 assert result.status == ApplicationStatus.SKIPPED
 assert 'Indeed-only' in result.error_message

@pytest.mark.asyncio
async def test_media_route_preserves_navigation_guard():
 from unittest.mock import AsyncMock,MagicMock
 from backend.browser.manager import BrowserManager
 context=MagicMock();context.route=AsyncMock()
 await BrowserManager._block_media(context)
 handler=context.route.await_args.args[1]
 route=MagicMock();route.request.resource_type='document';route.fallback=AsyncMock();route.continue_=AsyncMock()
 await handler(route)
 route.fallback.assert_awaited_once()
 route.continue_.assert_not_called()

@pytest.mark.asyncio
@pytest.mark.parametrize('url,frame_state,allowed', [
    ('https://smartapply.indeed.com/form', 'unavailable', True),
    ('https://external.test/apply', 'unavailable', False),
    ('https://external.test/apply', 'top', False),
    ('https://captcha.test/challenge', 'child', True),
])
@pytest.mark.parametrize('driver', ['local', 'cloud'])
async def test_navigation_guard_handles_new_windows_and_challenge_frames(monkeypatch, url, frame_state, allowed, driver):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from patchright.async_api import Error as LocalError
    from playwright.async_api import Error as CloudError
    Error = CloudError if driver == 'cloud' else LocalError
    from backend.browser.manager import BrowserManager
    from backend.shared.config import settings

    class Request:
        def is_navigation_request(self):
            return True

        @property
        def frame(self):
            if frame_state == 'unavailable':
                raise Error('Frame for this navigation request is not available')
            return SimpleNamespace(parent_frame=object() if frame_state == 'child' else None)

    monkeypatch.setattr(settings, 'INDEED_ONLY', True)
    context = MagicMock()
    context.route = AsyncMock()
    manager = BrowserManager()
    manager._running = True
    manager._mode = 'browserbase'
    manager._browser = SimpleNamespace(contexts=[context])
    await manager.new_context()
    handler = context.route.await_args.args[1]
    request = Request()
    request.url = url
    route = SimpleNamespace(request=request, abort=AsyncMock(), fallback=AsyncMock())
    await handler(route)
    assert route.fallback.await_count == int(allowed)
    assert route.abort.await_count == int(not allowed)
