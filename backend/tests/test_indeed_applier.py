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
    monkeypatch.setattr(IndeedApplier, '_check_answer', AsyncMock())
    monkeypatch.setattr(indeed_mod, 'resolve_application_question', AsyncMock(return_value=None))
    monkeypatch.setattr(indeed_mod, "mark_submission_intent", MagicMock(), raising=False)


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
    stage_page.file_input = MagicMock(count=AsyncMock(return_value=0), set_input_files=AsyncMock())
    stage_page.control = MagicMock(count=AsyncMock(return_value=1), is_visible=AsyncMock(return_value=True))
    stage_page.locator.side_effect = lambda selector: stage_page.file_input if selector == 'input[type="file"]' else stage_page.control
    stage_page.snapshot = AsyncMock(return_value=SimpleNamespace(
        formatted_tree='[1-1] button: Edit resume',
        xpath_map={'1-1': 'observed-resume-control'}))
    agent.browser.context.active_page = AsyncMock(return_value=stage_page)
    agent.extract = AsyncMock(side_effect=[SimpleNamespace(data=indeed_mod.NextStep(**d)) for d in decisions])
    agent.act = AsyncMock(return_value=SimpleNamespace(data=SimpleNamespace(success=True)))
    agent.observe = AsyncMock(return_value=SimpleNamespace(data=[]))
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
    agent = _stagehand(page, [dict(kind='park', instruction='', reason='Required answer missing')])
    agent.browser.context.active_page.return_value.file_input.count.return_value = 1
    await IndeedApplier(page, 's1', stagehand=agent).run(
        job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert 'including hidden inputs): 1' in agent.extract.await_args.args[0]
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_native_receipt_after_submit_preserves_uncertainty(monkeypatch):
    from types import SimpleNamespace
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [dict(kind=k, instruction=i, reason='') for k, i in [
        ('upload', ''), ('submit', 'Submit this application')]])
    agent.browser.context.active_page.return_value.snapshot.return_value = SimpleNamespace(formatted_tree='')
    applier = IndeedApplier(page, 's1', stagehand=agent)
    monkeypatch.setattr(applier, '_upload_original', AsyncMock())
    monkeypatch.setattr(applier, '_capture_screenshot', AsyncMock())
    monkeypatch.setattr(indeed_mod.asyncio, 'sleep', AsyncMock())
    result = await applier.run(job=_job(), user_profile={}, resume_text='Facts', cover_letter='')
    assert result.status == ApplicationStatus.FAILED
    assert result.error_category == ApplicationErrorCategory.SUBMISSION_UNCERTAIN
    agent.act.assert_awaited_once()


@pytest.mark.asyncio
async def test_saved_resume_cannot_continue_without_fresh_upload():
    page = _page('https://smartapply.indeed.com/form/resume-selection-module/resume-selection')
    agent = _stagehand(page, [dict(kind='act', instruction='Click Continue with the selected resume', reason='Same filename'),
                              dict(kind='park', instruction='', reason='Missing field')])
    await IndeedApplier(page, 's1', stagehand=agent).run(
        job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert agent.act.await_count == 1
    assert 'Resume options' in agent.act.await_args.args[0]
    assert 'Continue' not in agent.act.await_args.args[0]


@pytest.mark.asyncio
async def test_unsupported_factual_answer_is_queued_before_browser_action(monkeypatch):
    from backend.shared.application_rules import ApplicationParked
    page = _page()
    instruction = 'Select No for Is your current employer a customer of ServiceNow?'
    agent = _stagehand(page, [dict(kind='act', instruction=instruction, reason='Not mentioned')])
    applier = IndeedApplier(page, 's1', stagehand=agent)
    monkeypatch.setattr(applier, '_check_answer', AsyncMock(side_effect=ApplicationParked(
        'Is your current employer a customer of ServiceNow?')), raising=False)
    result = await applier.run(job=_job(), user_profile={}, resume_text='V2 Software LLC', cover_letter='')
    assert result.status == ApplicationStatus.SKIPPED
    assert result.error_category == ApplicationErrorCategory.NEEDS_INPUT
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
async def test_prefilled_unknown_answer_blocks_final_submit_even_after_upload(monkeypatch):
    from backend.shared.application_rules import ApplicationParked
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [dict(kind='upload', instruction='', reason='Attach resume'),
                              dict(kind='submit', instruction='Submit application', reason='Ready')])
    applier = IndeedApplier(page, 's1', stagehand=agent)
    monkeypatch.setattr(applier, '_upload_original', AsyncMock())
    checker = AsyncMock(side_effect=ApplicationParked('Is your employer a ServiceNow customer?'))
    monkeypatch.setattr(applier, '_check_answer', checker)
    result = await applier.run(job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert result.error_category == ApplicationErrorCategory.NEEDS_INPUT
    assert checker.await_args.kwargs['review'] is True
    agent.act.assert_not_awaited()
    assert not applier._submission_attempted


@pytest.mark.asyncio
async def test_resume_step_uploads_hidden_input_before_model_can_continue(monkeypatch):
    page = _page('https://smartapply.indeed.com/form/resume-selection-module/resume-selection')
    agent = _stagehand(page, [dict(kind='park', instruction='', reason='Missing field')])
    agent.browser.context.active_page.return_value.file_input.count.return_value = 1
    applier = IndeedApplier(page, 's1', stagehand=agent)
    upload = AsyncMock()
    monkeypatch.setattr(applier, '_upload_original', upload)
    await applier.run(job=_job(), user_profile={}, resume_text='', cover_letter='')
    upload.assert_awaited_once()
    assert 'uploaded in this application: True' in agent.extract.await_args.args[0]


@pytest.mark.asyncio
async def test_receipt_cannot_be_job_description_or_visible_submit():
    from types import SimpleNamespace
    page = _page()
    agent = _stagehand(page, [])
    native_page = agent.browser.context.active_page.return_value
    native_page.snapshot.return_value = SimpleNamespace(formatted_tree='[1-1] StaticText: application submitted')
    applier = IndeedApplier(page, 's1', stagehand=agent)
    assert not await applier._receipt()
    page.url = 'https://smartapply.indeed.com/form'
    assert await applier._receipt()
    native_page.snapshot.return_value.formatted_tree += '\n[1-2] button: Submit application'
    assert not await applier._receipt()



@pytest.mark.asyncio
async def test_upload_uses_saved_original_bytes(monkeypatch):
    page = _page()
    agent = _stagehand(page, [])
    native_page = agent.browser.context.active_page.return_value
    native_page.file_input.count.return_value = 1
    monkeypatch.setattr(indeed_mod, 'get_resume_bytes', lambda session: (b'canonical pdf', '.pdf'))
    await IndeedApplier(page, 's1', stagehand=agent)._upload_original(native_page)
    payload = native_page.file_input.set_input_files.await_args.args[0]
    from stagehand import FilePayload
    assert isinstance(payload, FilePayload)
    assert payload.buffer == b'canonical pdf'
    assert payload.mime_type == 'application/pdf'
    page.query_selector_all.assert_not_awaited()



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


@pytest.mark.asyncio
async def test_submit_intent_is_durable_before_click_and_survives_cancellation(monkeypatch):
    import asyncio
    order = []
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [dict(kind='upload', instruction='', reason=''),
                              dict(kind='submit', instruction='Submit application', reason='')])
    async def cancel_after_click(*args, **kwargs):
        order.append('click')
        raise asyncio.CancelledError()
    agent.act.side_effect = cancel_after_click
    marker = MagicMock(side_effect=lambda *args: order.append('durable intent'))
    monkeypatch.setattr(indeed_mod, 'mark_submission_intent', marker)
    applier = IndeedApplier(page, 's1', stagehand=agent)
    monkeypatch.setattr(applier, '_upload_original', AsyncMock())
    with pytest.raises(asyncio.CancelledError):
        await applier.run(job=_job(), user_profile={}, resume_text='', cover_letter='')
    marker.assert_called_once_with('s1', 'indeed-1')
    assert order == ['durable intent', 'click']


@pytest.mark.asyncio
async def test_submit_never_clicks_when_durable_intent_cannot_be_written(monkeypatch):
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [dict(kind='upload', instruction='', reason=''),
                              dict(kind='submit', instruction='Submit application', reason='')])
    monkeypatch.setattr(indeed_mod, 'mark_submission_intent', MagicMock(side_effect=RuntimeError('database offline')))
    applier = IndeedApplier(page, 's1', stagehand=agent)
    monkeypatch.setattr(applier, '_upload_original', AsyncMock())
    monkeypatch.setattr(applier, '_capture_screenshot', AsyncMock())
    result = await applier.run(job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert result.status == ApplicationStatus.FAILED
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
async def test_repeated_ineffective_selection_reobserves_before_atomic_dropdown_actions(monkeypatch):
    page = _page('https://smartapply.indeed.com/form/demographics')
    select = 'Select Decline To Self Identify in the Race/Ethnicity dropdown'
    agent = _stagehand(page, [dict(kind='act', instruction=i, reason='Optional demographic') for i in [
        select, select, 'Click the Race/Ethnicity dropdown to open it only',
        'Click the visible Decline To Self Identify option',
    ]] + [dict(kind='auth', instruction='', reason='Sign in required')])
    result = await IndeedApplier(page, 's1', stagehand=agent).run(
        job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert [call.args[0] for call in agent.act.await_args_list] == [
        select, 'Click the Race/Ethnicity dropdown to open it only',
        'Click the visible Decline To Self Identify option',
    ]
    recovery_prompt = agent.extract.await_args_list[2].args[0]
    assert 'Not executed: repeated instruction' in recovery_prompt
    assert result.error_category == ApplicationErrorCategory.AUTH_REQUIRED


@pytest.mark.asyncio
async def test_repeated_ineffective_action_still_has_bounded_stop(monkeypatch):
    page = _page()
    decision = dict(kind='act', instruction='Select the same dropdown option', reason='Required field')
    agent = _stagehand(page, [decision] * 3)
    applier = IndeedApplier(page, 's1', stagehand=agent)
    monkeypatch.setattr(applier, '_capture_screenshot', AsyncMock())
    result = await applier.run(job=_job(), user_profile={}, resume_text='', cover_letter='')
    agent.act.assert_awaited_once()
    assert result.status == ApplicationStatus.FAILED
    assert 'not progressing' in result.error_message


@pytest.mark.asyncio
async def test_direct_review_opens_visible_resume_edit_then_requires_fresh_upload(monkeypatch):
    from types import SimpleNamespace
    page = _page('https://smartapply.indeed.com/form/review')
    from stagehand import Action
    observed = Action(method='click', description='Click Edit resume', selector='observed-resume-control', arguments=[])
    agent = _stagehand(page, [dict(kind=k, instruction=i, reason='') for k,i in [
        ('submit', 'Submit application'), ('upload', ''), ('submit', 'Submit application')]])
    agent.observe.return_value.data = [observed]
    control = agent.browser.context.active_page.return_value.control
    applier = IndeedApplier(page, 's1', stagehand=agent)
    upload = AsyncMock()
    monkeypatch.setattr(applier, '_upload_original', upload)
    monkeypatch.setattr(applier, '_receipt', AsyncMock(return_value=True))
    monkeypatch.setattr(applier, '_capture_screenshot', AsyncMock())
    check_answer = AsyncMock()
    monkeypatch.setattr(applier, '_check_answer', check_answer)
    monkeypatch.setattr(indeed_mod.asyncio, 'sleep', AsyncMock())
    result = await applier.run(job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert result.status == ApplicationStatus.SUBMITTED
    upload.assert_awaited_once()
    agent.observe.assert_awaited_once()
    assert agent.act.await_args_list[0].args[0] is observed
    assert agent.act.await_args_list[1].args[0] == 'Submit application'
    control.is_visible.assert_awaited_once()
    assert 'resume-edit' in check_answer.await_args_list[0].args[0]


@pytest.mark.asyncio
async def test_direct_review_resume_recovery_is_one_attempt_only(monkeypatch):
    from types import SimpleNamespace
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [dict(kind='submit', instruction='Submit application', reason='')] * 2)
    observed = SimpleNamespace(method='click', description='Click Edit resume', selector='observed-resume-control')
    agent.observe.return_value.data = [observed]
    result = await IndeedApplier(page, 's1', stagehand=agent).run(job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert result.status == ApplicationStatus.SKIPPED
    agent.act.assert_awaited_once_with(observed, page=agent.browser.context.active_page.return_value, timeout=45000)
    agent.observe.assert_awaited_once()
    indeed_mod.mark_submission_intent.assert_not_called()


@pytest.mark.asyncio
async def test_direct_review_cannot_click_hidden_resume_edit(monkeypatch):
    from types import SimpleNamespace
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [dict(kind='submit', instruction='Submit application', reason='')])
    agent.observe.return_value.data = [SimpleNamespace(method='click', description='Click Edit resume', selector='hidden-control')]
    agent.browser.context.active_page.return_value.control.is_visible.return_value = False
    result = await IndeedApplier(page, 's1', stagehand=agent).run(job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert result.status == ApplicationStatus.SKIPPED
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('method,label', [('click', 'Submit application'), ('click', 'Edit contact information'), ('fill', 'Edit resume')])
async def test_resume_recovery_rejects_submit_other_fields_and_non_clicks(monkeypatch, method, label):
    from types import SimpleNamespace
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [dict(kind='submit', instruction='Submit application', reason='')])
    agent.observe.return_value.data = [SimpleNamespace(method=method, description='Edit resume', selector='observed-control')]
    agent.browser.context.active_page.return_value.snapshot.return_value = SimpleNamespace(
        formatted_tree=f'[1-1] button: {label}', xpath_map={'1-1': 'observed-control'})
    result = await IndeedApplier(page, 's1', stagehand=agent).run(job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert result.status == ApplicationStatus.SKIPPED
    agent.act.assert_not_awaited()
    indeed_mod.mark_submission_intent.assert_not_called()


@pytest.mark.asyncio
async def test_observed_iframe_selector_is_delegated_unchanged_to_native_stagehand():
    from types import SimpleNamespace
    page = _page('https://smartapply.indeed.com/form/review')
    selector = 'xpath=/html[1]/body[1]/iframe[1]/html[1]/body[1]/button[1]'
    agent = _stagehand(page, [dict(kind='submit', instruction='Submit application', reason='')] * 2)
    native_page = agent.browser.context.active_page.return_value
    native_page.snapshot.return_value = SimpleNamespace(
        formatted_tree='[11-2319] button: Edit resume\n  [11-2320] StaticText: Edit',
        xpath_map={'11-2319': selector.removeprefix('xpath=')})
    observed = SimpleNamespace(method='click', description='Click Edit resume', selector=selector)
    agent.observe.return_value.data = [observed]
    result = await IndeedApplier(page, 's1', stagehand=agent).run(job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert result.status == ApplicationStatus.SKIPPED  # fresh upload still required
    native_page.locator.assert_any_call(selector)
    agent.act.assert_awaited_once_with(observed, page=native_page, timeout=45000)
    native_page.snapshot.assert_awaited_once_with(include_iframes=True)
    page.locator.assert_not_called()
    page.frame_locator.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('count', [0, 2])
async def test_native_upload_requires_unique_file_input(monkeypatch, count):
    from backend.shared.application_rules import ApplicationParked
    agent = _stagehand(_page(), [])
    native_page = agent.browser.context.active_page.return_value
    native_page.file_input.count.return_value = count
    monkeypatch.setattr(indeed_mod, 'get_resume_bytes', lambda session: (b'pdf', '.pdf'))
    with pytest.raises(ApplicationParked):
        await IndeedApplier(_page(), 's1', stagehand=agent)._upload_original(native_page)
    native_page.file_input.set_input_files.assert_not_awaited()


@pytest.mark.asyncio
async def test_observed_employer_redirect_queues_without_filling():
    url = 'https://openai.com/careers/applied-ai-engineer-enterprise-san-francisco/'
    page = _page(url)
    page.context._jobhunter_external_redirect = None
    agent = _stagehand(page, [])
    result = await IndeedApplier(page, 's1', stagehand=agent)._drive(_job(), {}, '', '')
    assert result.status == ApplicationStatus.QUEUED
    assert result.external_application_url == url
    agent.extract.assert_not_awaited()
    agent.act.assert_not_awaited()
    page.query_selector_all.assert_not_awaited()
    page.evaluate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('url', [
    'http://openai.com/careers/role', 'https://127.0.0.1/apply',
    'https://example.local/apply', 'https://user:pass@openai.com/apply', 'about:blank',
])
async def test_observed_employer_redirect_rejects_unsafe_destinations(url):
    page = _page(url)
    page.context._jobhunter_external_redirect = None
    agent = _stagehand(page, [])
    result = await IndeedApplier(page, 's1', stagehand=agent)._drive(_job(), {}, '', '')
    assert result.status == ApplicationStatus.FAILED
    assert not result.external_application_url
    agent.extract.assert_not_awaited()
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
async def test_observed_employer_redirect_requires_indeed_source():
    page = _page('https://openai.com/careers/role')
    page.context._jobhunter_external_redirect = None
    agent = _stagehand(page, [])
    result = await IndeedApplier(page, 's1', stagehand=agent)._drive(
        _job('https://example.com/job'), {}, '', '')
    assert result.status == ApplicationStatus.FAILED
    assert not result.external_application_url


# Preserve the implementation before the autouse fixture replaces this method.
_check_answer_with_frames = IndeedApplier._check_answer


@pytest.mark.asyncio
async def test_native_iframe_snapshot_is_used_for_final_answer_audit(monkeypatch):
    from types import SimpleNamespace
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [])
    native_page = agent.browser.context.active_page.return_value
    tree = '[1-1] heading: Review\n[1-2] Iframe\n  [2-1] StaticText: Work authorization: Yes'
    native_page.snapshot.return_value = SimpleNamespace(formatted_tree=tree)
    checker = AsyncMock()
    monkeypatch.setattr('backend.browser.application_answers.check_application_answer', checker)
    await _check_answer_with_frames(IndeedApplier(page, 's1', stagehand=agent), 'Submit', '{}', review=True)
    assert checker.await_args.kwargs['review_text'] == tree
    native_page.snapshot.assert_awaited_once_with(include_iframes=True)
    page.evaluate.assert_not_awaited()
    page.frame_locator.assert_not_called()


@pytest.mark.asyncio
async def test_native_receipt_requires_no_submit_button_in_visible_snapshot():
    from types import SimpleNamespace
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [])
    native_page = agent.browser.context.active_page.return_value
    native_page.snapshot.return_value = SimpleNamespace(formatted_tree=(
        '[1-1] Iframe\n  [2-1] StaticText: Your application has been submitted\n'
        '[1-2] Iframe\n  [3-1] button: Submit application'))
    applier = IndeedApplier(page, 's1', stagehand=agent)
    assert not await applier._receipt()
    native_page.snapshot.return_value.formatted_tree = '[2-1] StaticText: Your application has been submitted'
    assert await applier._receipt()
    native_page.snapshot.return_value.formatted_tree = '[2-1] heading: Review application'
    assert not await applier._receipt()


@pytest.mark.asyncio
async def test_native_snapshot_read_retries_detached_frame_without_browser_actions(monkeypatch):
    from types import SimpleNamespace
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [])
    native_page = agent.browser.context.active_page.return_value
    native_page.snapshot.side_effect = [RuntimeError('frame detached'), SimpleNamespace(formatted_tree='[1-1] heading: Review')]
    monkeypatch.setattr(indeed_mod.asyncio, 'sleep', AsyncMock())
    result = await IndeedApplier(page, 's1', stagehand=agent)._visible_application_snapshot()
    assert result['text'] == '[1-1] heading: Review'
    assert native_page.snapshot.await_count == 2
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [RuntimeError('detached during inspection'), None])
async def test_native_snapshot_read_failure_or_empty_content_blocks_final_audit(monkeypatch, error):
    from types import SimpleNamespace
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [])
    native_page = agent.browser.context.active_page.return_value
    native_page.snapshot.side_effect = error
    native_page.snapshot.return_value = SimpleNamespace(formatted_tree='')
    checker = AsyncMock()
    monkeypatch.setattr('backend.browser.application_answers.check_application_answer', checker)
    monkeypatch.setattr(indeed_mod.asyncio, 'sleep', AsyncMock())
    with pytest.raises((RuntimeError, indeed_mod.ApplicationParked)):
        await _check_answer_with_frames(IndeedApplier(page, 's1', stagehand=agent), 'Submit', '{}', review=True)
    assert native_page.snapshot.await_count == 3
    checker.assert_not_awaited()
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_payload_serializes_through_installed_stagehand_sdk(monkeypatch):
    import base64
    from stagehand.locator import Locator
    agent = _stagehand(_page(), [])
    native_page = agent.browser.context.active_page.return_value
    rpc = MagicMock(send=AsyncMock(side_effect=[1, None]))
    native_page.locator.side_effect = lambda selector: Locator(rpc, page_id='native-tab', selector=selector)
    monkeypatch.setattr(indeed_mod, 'get_resume_bytes', lambda session: (b'canonical pdf', '.pdf'))
    await IndeedApplier(_page(), 's1', stagehand=agent)._upload_original(native_page)
    method, params, _ = rpc.send.await_args.args
    assert method == 'locator.set_input_files'
    assert params.page_id == 'native-tab'
    assert params.selector == 'input[type="file"]'
    assert params.files[0].name == 'Resume.pdf'
    assert params.files[0].mime_type == 'application/pdf'
    assert base64.b64decode(params.files[0].data) == b'canonical pdf'


@pytest.mark.parametrize('tree,paths', [
    ('[1-1] button: Edit resume', {'1-1': 'other-control'}),
    ('[1-1] button: Edit resume\n[1-2] button: Edit resume',
     {'1-1': 'control', '1-2': 'control'}),
])
def test_resume_label_requires_unique_snapshot_match(tree, paths):
    from types import SimpleNamespace
    assert indeed_mod._snapshot_control_label(SimpleNamespace(
        formatted_tree=tree, xpath_map=paths), 'control') == ''


@pytest.mark.asyncio
async def test_same_continue_instruction_progresses_across_wizard_steps_at_same_url():
    from types import SimpleNamespace
    page = _page('https://smartapply.indeed.com/form')
    instruction = 'Click Continue'
    agent = _stagehand(page, [dict(kind='act', instruction=instruction, reason='Next step')] * 3 +
                       [dict(kind='auth', instruction='', reason='Sign in required')])
    native_page = agent.browser.context.active_page.return_value
    native_page.snapshot.side_effect = [SimpleNamespace(formatted_tree=tree) for tree in [
        '[1-1] heading: Contact information\n[1-2] button: Continue',
        '[2-1] heading: Experience\n[2-2] button: Continue',
        '[3-1] heading: Voluntary demographics\n[3-2] button: Continue',
    ]]
    result = await IndeedApplier(page, 's1', stagehand=agent).run(
        job=_job(), user_profile={}, resume_text='', cover_letter='')
    assert agent.act.await_count == 3
    assert all(call.args[0] == instruction for call in agent.act.await_args_list)
    assert result.error_category == ApplicationErrorCategory.AUTH_REQUIRED


@pytest.mark.asyncio
async def test_snapshot_node_id_changes_do_not_bypass_unchanged_form_stop(monkeypatch):
    from types import SimpleNamespace
    page = _page('https://smartapply.indeed.com/form')
    agent = _stagehand(page, [dict(kind='act', instruction='Click Continue', reason='Next')] * 3)
    native_page = agent.browser.context.active_page.return_value
    native_page.snapshot.side_effect = [SimpleNamespace(formatted_tree=(
        f'[{n}-1] heading: Experience\n  [{n}-2] textbox: Required answer\n'
        f'[{n}-3] button: Continue')) for n in range(1, 4)]
    applier = IndeedApplier(page, 's1', stagehand=agent)
    monkeypatch.setattr(applier, '_capture_screenshot', AsyncMock())
    result = await applier.run(job=_job(), user_profile={}, resume_text='', cover_letter='')
    agent.act.assert_awaited_once()
    assert result.status == ApplicationStatus.FAILED
    assert 'not progressing' in result.error_message


@pytest.mark.asyncio
async def test_parked_resume_fact_gets_one_judge_suggestion_then_normal_action_audit(monkeypatch):
    from backend.browser.application_answers import AnswerSuggestion, AnswerEvidence
    question = 'Do you have Anthropic experience?'
    resume = 'Built an application using Anthropic APIs.'
    suggestion = AnswerSuggestion(supported=True, answer='Yes', reason='Hands-on API project.',
        evidence=[AnswerEvidence(source='resume', quote=resume)])
    resolver = AsyncMock(return_value=suggestion)
    monkeypatch.setattr(indeed_mod, 'resolve_application_question', resolver)
    page = _page()
    agent = _stagehand(page, [dict(kind='park', instruction='', reason=question),
                             dict(kind='act', instruction='Choose Yes for Anthropic experience', reason='Resume supports it'),
                             dict(kind='auth', instruction='', reason='Sign in')])
    applier = IndeedApplier(page, 's1')
    applier.stagehand = agent
    check = AsyncMock()
    monkeypatch.setattr(applier, '_check_answer', check)
    await applier.run(job=_job(), user_profile={}, resume_text=resume, cover_letter='')
    resolver.assert_awaited_once()
    assert resume in resolver.await_args.args[1]
    assert 'Resume-grounded answer suggestion' in agent.extract.await_args_list[1].args[0]
    assert '"answer": "Yes"' in agent.extract.await_args_list[1].args[0]
    check.assert_awaited_once()
    agent.act.assert_awaited_once()
    indeed_mod.mark_submission_intent.assert_not_called()


@pytest.mark.asyncio
async def test_park_adjudication_cannot_repeat_or_force_an_answer(monkeypatch):
    from backend.browser.application_answers import AnswerSuggestion, AnswerEvidence
    suggestion = AnswerSuggestion(supported=True, answer='Yes', reason='Resume support.',
        evidence=[AnswerEvidence(source='resume', quote='API project')])
    resolver = AsyncMock(return_value=suggestion)
    monkeypatch.setattr(indeed_mod, 'resolve_application_question', resolver)
    agent = _stagehand(_page(), [dict(kind='park', instruction='', reason='Exact required question?')] * 2)
    result = await IndeedApplier(_page(), 's1', stagehand=agent).run(
        job=_job(), user_profile={}, resume_text='API project', cover_letter='')
    assert result.error_category == ApplicationErrorCategory.NEEDS_INPUT
    assert result.error_message == 'Exact required question?'
    resolver.assert_awaited_once()
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejected_prefilled_answer_is_corrected_before_any_submit(monkeypatch):
    from backend.browser.application_answers import AnswerSuggestion, AnswerEvidence
    question = 'Do you possess Anthropic Experience and Certifications?'
    rules = 'No formal Anthropic certification; answer No to the combined question.'
    resolver = AsyncMock(return_value=AnswerSuggestion(supported=True, answer='No', reason='Owner rule.',
        evidence=[AnswerEvidence(source='application_rules', quote=rules)]))
    monkeypatch.setattr(indeed_mod, 'resolve_application_question', resolver)
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [dict(kind=k, instruction=i, reason='') for k, i in [
        ('upload', ''), ('submit', 'Submit application'),
        ('act', 'Change combined Anthropic experience and certification answer to No'),
        ('submit', 'Submit application')]])
    applier = IndeedApplier(page, 's1', application_rules=rules, stagehand=agent)
    monkeypatch.setattr(applier, '_upload_original', AsyncMock())
    check = AsyncMock(side_effect=[indeed_mod.ApplicationParked(question), None, None])
    monkeypatch.setattr(applier, '_check_answer', check)
    monkeypatch.setattr(applier, '_receipt', AsyncMock(return_value=True))
    monkeypatch.setattr(applier, '_capture_screenshot', AsyncMock())
    monkeypatch.setattr(indeed_mod.asyncio, 'sleep', AsyncMock())
    result = await applier.run(job=_job(), user_profile={}, resume_text='Anthropic APIs', cover_letter='')
    assert result.status == ApplicationStatus.SUBMITTED
    assert [c.args[0] for c in agent.act.await_args_list] == [
        'Change combined Anthropic experience and certification answer to No', 'Submit application']
    assert check.await_count == 3
    indeed_mod.mark_submission_intent.assert_called_once()
    resolver.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_but_irrelevant_resume_quote_cannot_override_certification_audit(monkeypatch):
    from backend.browser.application_answers import AnswerSuggestion, AnswerEvidence
    question = 'Do you hold an Anthropic certification?'
    # A genuine quote proves provenance, not that the suggested credential is true.
    resolver = AsyncMock(return_value=AnswerSuggestion(supported=True, answer='Yes',
        reason='Incorrect inference from API use.',
        evidence=[AnswerEvidence(source='resume', quote='Built an application using Anthropic APIs.')]))
    monkeypatch.setattr(indeed_mod, 'resolve_application_question', resolver)
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [dict(kind=k, instruction=i, reason='') for k, i in [
        ('upload', ''), ('submit', 'Submit application'), ('submit', 'Submit application')]])
    applier = IndeedApplier(page, 's1', stagehand=agent)
    monkeypatch.setattr(applier, '_upload_original', AsyncMock())
    audit = AsyncMock(side_effect=indeed_mod.ApplicationParked(question))
    monkeypatch.setattr(applier, '_check_answer', audit)
    result = await applier.run(job=_job(), user_profile={},
        resume_text='Built an application using Anthropic APIs.', cover_letter='')
    assert result.error_category == ApplicationErrorCategory.NEEDS_INPUT
    assert result.error_message == question
    assert audit.await_count == 2
    resolver.assert_awaited_once()
    agent.act.assert_not_awaited()
    indeed_mod.mark_submission_intent.assert_not_called()
