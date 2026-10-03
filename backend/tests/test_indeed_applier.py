"""Indeed Apply applier: routing, loud selector failures, logged-in gating."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.browser import browserbase_client as bbc
from backend.browser.tools.appliers import dispatcher, indeed as indeed_mod
from backend.browser.tools.appliers.indeed import IndeedApplier
from backend.browser.tools.ats_detector import detect_ats_from_url
from backend.orchestrator.agents import application as app_node
from backend.shared.config import settings
from backend.shared.models.schemas import (
    ApplicationErrorCategory,
    ApplicationStatus,
    ATSType,
    JobBoard,
    JobListing,
)


def _job(url: str = "https://www.indeed.com/viewjob?jk=abc123") -> JobListing:
    return JobListing(
        id="indeed-1",
        title="Senior Engineer",
        company="Acme",
        location="Austin, TX",
        url=url,
        board=JobBoard.INDEED,
        ats_type=ATSType.UNKNOWN,
        is_easy_apply=True,
        discovered_at=datetime.utcnow(),
    )


@pytest.fixture(autouse=True)
def _no_selector_db(monkeypatch):
    """_click_selector consults the selector-ranking DB; keep tests in-process."""
    monkeypatch.setattr("backend.browser.tools.appliers.base.get_top_selectors", lambda *a, **k: [])
    monkeypatch.setattr("backend.browser.tools.appliers.base.record_success", lambda *a, **k: None)
    monkeypatch.setattr("backend.browser.tools.appliers.base.record_failure", lambda *a, **k: None)
    monkeypatch.setattr("backend.browser.tools.appliers.base.emit_agent_event", AsyncMock())


# ---------------------------------------------------------------------------
# detection + routing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url", [
    "https://www.indeed.com/viewjob?jk=abc123",
    "https://indeed.com/viewjob?jk=abc123",
    "https://uk.indeed.com/viewjob?jk=abc123",
    "https://smartapply.indeed.com/beta/indeedapply/form/contact-info",
])
def test_detect_ats_recognises_indeed(url):
    assert detect_ats_from_url(url) == ATSType.INDEED


def test_detect_ats_does_not_match_lookalike_hosts():
    assert detect_ats_from_url("https://notindeed.com/jobs/1") == ATSType.UNKNOWN
    assert detect_ats_from_url("https://boards.greenhouse.io/acme/jobs/1") == ATSType.GREENHOUSE


@pytest.mark.asyncio
async def test_dispatcher_routes_indeed_urls_to_indeed_applier(monkeypatch):
    run = AsyncMock(return_value=MagicMock(status=ApplicationStatus.SUBMITTED))
    monkeypatch.setattr(IndeedApplier, "run", run)
    page = MagicMock(url="https://www.indeed.com/viewjob?jk=abc123")

    await dispatcher.apply_with_playwright(
        job=_job(), user_profile={}, resume_text="", cover_letter="",
        resume_file_path=None, session_id="s1", page=page,
    )

    run.assert_awaited_once()
    assert dispatcher._APPLIER_MAP[ATSType.INDEED] is IndeedApplier


# ---------------------------------------------------------------------------
# applier behaviour
# ---------------------------------------------------------------------------


def _page(url: str = "https://www.indeed.com/viewjob?jk=abc123"):
    page = MagicMock()
    page.url = url
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.wait_for_selector = AsyncMock(side_effect=TimeoutError("no element"))
    page.evaluate = AsyncMock(return_value=[])
    page.wait_for_load_state = AsyncMock()
    return page


def _stagehand(page, decisions):
    from types import SimpleNamespace
    agent = MagicMock()
    stage_page = MagicMock()
    stage_page.url = AsyncMock(side_effect=lambda: page.url)
    agent.browser.context.active_page = AsyncMock(return_value=stage_page)
    agent.extract = AsyncMock(side_effect=[SimpleNamespace(data=indeed_mod.NextStep(**d)) for d in decisions])
    agent.act = AsyncMock(return_value=SimpleNamespace(data=SimpleNamespace(success=True)))
    agent.metrics = AsyncMock()
    page.context.pages = [page]
    return agent


@pytest.mark.asyncio
async def test_missing_stagehand_fails_without_selector_fallback():
    applier = IndeedApplier(_page(), 's1')
    result = await applier.run(job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert result.status == ApplicationStatus.FAILED
    assert 'Stagehand is unavailable' in result.error_message


@pytest.mark.asyncio
async def test_auth_and_missing_answers_do_not_act():
    for kind, status in [('auth', ApplicationStatus.FAILED), ('park', ApplicationStatus.SKIPPED)]:
        page = _page()
        agent = _stagehand(page, [dict(kind=kind, instruction='', reason='Work authorization?')])
        result = await IndeedApplier(page, 's1', stagehand=agent).run(
            job=_job(), user_profile={}, resume_text='', cover_letter='')
        assert result.status == status
        assert result.error_message == 'Work authorization?'
        agent.act.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_requires_original_resume_upload():
    page = _page()
    agent = _stagehand(page, [dict(kind='submit', instruction='Submit application', reason='Ready')])
    result = await IndeedApplier(page, 's1', stagehand=agent).run(
        job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert result.status == ApplicationStatus.SKIPPED
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('receipt', [True, False])
async def test_natural_actions_upload_and_single_submit_need_receipt(monkeypatch, receipt):
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [dict(kind=k, instruction=i, reason='') for k,i in [
        ('act', 'Fill the name with Ada'), ('upload', ''), ('submit', 'Submit this application')]])
    applier = IndeedApplier(page, 's1', stagehand=agent)
    upload = AsyncMock()
    monkeypatch.setattr(applier, '_upload_original', upload)
    monkeypatch.setattr(applier, '_receipt', AsyncMock(return_value=receipt))
    monkeypatch.setattr(applier, '_capture_screenshot', AsyncMock())
    monkeypatch.setattr(indeed_mod.asyncio, 'sleep', AsyncMock())
    result = await applier.run(job=_job(), user_profile={'name': 'Ada'}, resume_text='Facts', cover_letter='Cover')
    assert result.status == (ApplicationStatus.SUBMITTED if receipt else ApplicationStatus.FAILED)
    if not receipt:
        assert result.error_category == ApplicationErrorCategory.SUBMISSION_UNCERTAIN
    assert agent.act.await_count == 2
    upload.assert_awaited_once()
    assert 'Never guess required answers' in agent.extract.await_args.args[0]


@pytest.mark.asyncio
async def test_hidden_file_input_is_reported_to_stagehand(monkeypatch):
    page = _page('https://smartapply.indeed.com/form/resume')
    page.query_selector_all.return_value = [MagicMock()]
    agent = _stagehand(page, [dict(kind='park', instruction='', reason='Required answer missing')])
    await IndeedApplier(page, 's1', stagehand=agent).run(
        job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert 'including hidden inputs): 1' in agent.extract.await_args.args[0]
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
async def test_receipt_cannot_be_job_description_or_visible_submit():
    page = _page()
    page.evaluate = AsyncMock(return_value={'text': 'application submitted', 'submitting': False})
    applier = IndeedApplier(page, 's1')
    assert not await applier._receipt()
    page.url = 'https://smartapply.indeed.com/form'
    assert await applier._receipt()
    page.evaluate.return_value['submitting'] = True
    assert not await applier._receipt()


@pytest.mark.asyncio
async def test_upload_uses_saved_original_bytes(monkeypatch):
    page = _page()
    field = MagicMock(set_input_files=AsyncMock())
    page.query_selector_all = AsyncMock(return_value=[field])
    monkeypatch.setattr(indeed_mod, 'get_resume_bytes', lambda session: (b'canonical pdf', '.pdf'))
    await IndeedApplier(page, 's1')._upload_original()
    assert field.set_input_files.await_args.args[0]['buffer'] == b'canonical pdf'


# ---------------------------------------------------------------------------
# application-node gating
# ---------------------------------------------------------------------------


def test_board_login_available_requires_browserbase_mode_and_context(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_MODE", "browserbase")
    monkeypatch.setattr(bbc, "config_for_user", lambda uid: bbc.BrowserbaseConfig(context_ids={"indeed": "ctx-indeed"}))
    assert app_node._board_login_available(JobBoard.INDEED, "user-1") is True
    assert app_node._board_login_available("indeed", "user-1") is True
    assert app_node._board_login_available(JobBoard.GLASSDOOR, "user-1") is False

    monkeypatch.setattr(bbc, "config_for_user", lambda uid: bbc.BrowserbaseConfig(context_ids={"default": "ctx-default"}))
    assert app_node._board_login_available(JobBoard.INDEED, "user-1") is False  # default ctx is not a login

    monkeypatch.setattr(settings, "BROWSER_MODE", "cdp")
    monkeypatch.setattr(bbc, "config_for_user", lambda uid: bbc.BrowserbaseConfig(context_ids={"indeed": "ctx-indeed"}))
    assert app_node._board_login_available(JobBoard.INDEED, "user-1") is False

@pytest.mark.asyncio
async def test_exception_during_submit_is_not_retryable(monkeypatch):
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [dict(kind='upload', instruction='', reason=''),
                              dict(kind='submit', instruction='Submit application', reason='')])
    agent.act.side_effect = TimeoutError('response lost after click')
    applier = IndeedApplier(page, 's1', stagehand=agent)
    monkeypatch.setattr(applier, '_upload_original', AsyncMock())
    result = await applier.run(job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert result.error_category == ApplicationErrorCategory.SUBMISSION_UNCERTAIN
    agent.act.assert_awaited_once()


@pytest.mark.asyncio
async def test_loading_page_waits_without_actions_or_premature_failure(monkeypatch):
    page = _page()
    agent = _stagehand(page, [dict(kind='wait', instruction='', reason='The form is loading')]*3 +
                       [dict(kind='auth', instruction='', reason='Sign in required')])
    monkeypatch.setattr(indeed_mod.asyncio, 'sleep', AsyncMock())
    result = await IndeedApplier(page, 's1', stagehand=agent).run(
        job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert result.error_category == ApplicationErrorCategory.AUTH_REQUIRED
    assert agent.extract.await_count == 4
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_action_is_reobserved_with_history_and_bounded(monkeypatch):
    from types import SimpleNamespace
    page = _page()
    agent = _stagehand(page, [dict(kind='act', instruction=f'Choose option {n}', reason='Required field')
                              for n in range(3)])
    agent.act.return_value = SimpleNamespace(data=SimpleNamespace(success=False, message='Option not found'))
    applier = IndeedApplier(page, 's1', stagehand=agent)
    capture = AsyncMock()
    monkeypatch.setattr(applier, '_capture_screenshot', capture)
    result = await applier.run(job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert agent.extract.await_count == 3
    assert 'Option not found' in agent.extract.await_args.args[0]
    assert 'Choose option 1' in agent.extract.await_args.args[0]
    assert result.status == ApplicationStatus.FAILED
    assert 'Choose option 2' in result.error_message
    capture.assert_awaited_once()
