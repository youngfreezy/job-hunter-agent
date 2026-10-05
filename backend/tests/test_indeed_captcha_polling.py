"""Passive verification decisions are reused only on unchanged native state."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.browser.captcha_monitor import CaptchaMonitor
from backend.browser.grounded_actions import ActionDeferred, GroundedAction
from backend.browser.tools.appliers import indeed as mod
from backend.shared.application_rules import ApplicationParked
from backend.tests.test_indeed_applier import _job, _page, _stagehand

URL = 'https://smartapply.indeed.com/form/review'
CHALLENGE = '[1] main:\n  [2] checkbox: Verify you are human'


def _scenario(monkeypatch, decisions, *, url=URL):
    page = _page(url)
    agent = _stagehand(page, decisions)
    native = agent.browser.context.active_page.return_value
    native.page_id = 'application-tab'
    native.snapshot.side_effect = None
    native.snapshot.return_value = SimpleNamespace(formatted_tree=CHALLENGE, xpath_map={})
    native.goto = AsyncMock()
    monitor = CaptchaMonitor()
    agent._jobhunter_captcha_monitor = monitor
    applier = mod.IndeedApplier(page, 'offline-captcha', stagehand=agent)
    applier._application_deadline_at = asyncio.get_running_loop().time() + 700
    monkeypatch.setattr(applier, '_emit_step', AsyncMock())
    monkeypatch.setattr(mod, 'resolve_application_question', AsyncMock(return_value=None))
    return applier, agent, native, page, monitor


def _decision(kind='captcha'):
    return dict(kind=kind, instruction='', reason='Required factual answer' if kind == 'park' else 'Verification remains visible')


def _assert_no_mutation(agent, native):
    agent.native_action.assert_not_awaited()
    agent.act.assert_not_awaited()
    native.goto.assert_not_awaited()
    native.file_input.set_input_files.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_finished_generation_gets_visual_then_native_polling_on_one_deadline(monkeypatch):
    applier, agent, native, _, monitor = _scenario(monkeypatch, [_decision()] * 10)
    monitor.record('browserbase-solving-started')
    monitor.record('browserbase-solving-finished')
    deadlines = []

    async def passive_sleep(seconds):
        assert 0 < seconds <= mod.CAPTCHA_POLL_SECONDS
        deadlines.append(applier._captcha_deadline_at)
        native.snapshot.return_value.formatted_tree = CHALLENGE.replace('[', f'[poll-{len(deadlines)}-')
        if len(deadlines) == 3:
            applier._captcha_deadline_at = asyncio.get_running_loop().time() - 1

    monkeypatch.setattr(mod.asyncio, 'sleep', AsyncMock(side_effect=passive_sleep))
    result = await applier._drive(_job(), {}, '', '')
    assert result.error_category.value == 'captcha'
    assert len(deadlines) == 3 and len(set(deadlines)) == 1
    assert agent.extract.await_count == 2
    assert agent.extract.await_args_list[0].kwargs['screenshot'] is True
    assert not agent.extract.await_args_list[1].kwargs.get('screenshot')
    assert agent.extract.await_args.kwargs['cache'] is False
    _assert_no_mutation(agent, native)


@pytest.mark.asyncio
@pytest.mark.parametrize('url', [URL, 'https://smartapply.indeed.com/form/resume-selection'])
async def test_solver_finish_invalidates_captcha_but_does_not_authorize_progress(monkeypatch, url):
    applier, agent, native, _, monitor = _scenario(monkeypatch, [_decision()] * 10, url=url)
    native.file_input.count.return_value = 1
    monitor.record('browserbase-solving-started')

    async def finish(**kwargs):
        monitor.record('browserbase-solving-finished')

    monitor.wait_until_idle = AsyncMock(side_effect=finish)
    polls = 0

    async def passive_sleep(seconds):
        nonlocal polls
        polls += 1
        if polls == 3:
            applier._captcha_deadline_at = asyncio.get_running_loop().time() - 1

    monkeypatch.setattr(mod.asyncio, 'sleep', AsyncMock(side_effect=passive_sleep))
    result = await applier._drive(_job(), {}, '', '')
    assert result.error_category.value == 'captcha'
    assert agent.extract.await_count == 2  # Visual decision, then a separately bound native decision.
    assert agent.extract.await_args_list[0].kwargs.get('screenshot') is True
    assert not agent.extract.await_args_list[1].kwargs.get('screenshot')
    assert all(call.kwargs['cache'] is False for call in agent.extract.await_args_list)
    monitor.wait_until_idle.assert_awaited_once()
    _assert_no_mutation(agent, native)


@pytest.mark.asyncio
async def test_model_decision_spanning_finished_solve_is_discarded(monkeypatch):
    applier, agent, native, _, monitor = _scenario(monkeypatch, [_decision('upload'), _decision('park')])
    extract = agent.extract.side_effect

    async def classify(*args, **kwargs):
        result = await extract(*args, **kwargs)
        if agent.extract.await_count == 1:
            monitor.record('browserbase-solving-started')
            monitor.record('browserbase-solving-finished')
        return result

    agent.extract.side_effect = classify
    with pytest.raises(ApplicationParked, match='Required factual answer'):
        await applier._drive(_job(), {}, '', '')
    assert agent.extract.await_count == 2
    assert agent.extract.await_args.kwargs['screenshot'] is True
    _assert_no_mutation(agent, native)


@pytest.mark.asyncio
@pytest.mark.parametrize('resume_edit', [False, True])
@pytest.mark.parametrize('timing', ['audit', 'event'])
async def test_verification_start_during_audit_or_event_defers_native_action(monkeypatch, resume_edit, timing):
    step = dict(kind='submit' if resume_edit else 'act', instruction='Continue', reason='')
    applier, agent, native, _, monitor = _scenario(monkeypatch, [step])
    label = 'Edit resume' if resume_edit else 'Continue'
    native.snapshot.return_value = SimpleNamespace(
        formatted_tree=f'[1] button: {label}', xpath_map={'1': 'observed-resume-control'})
    agent.observe.return_value = SimpleNamespace(data=[SimpleNamespace(
        method='click', selector='observed-resume-control', arguments=[])])

    async def audit(*args, **kwargs):
        if timing == 'audit': monitor.record('browserbase-solving-started')

    async def emit(message):
        if timing == 'event' and message in ('Stagehand: Continue', 'Opening the resume editor to attach your supplied file...'):
            monitor.record('browserbase-solving-started')

    monkeypatch.setattr(applier, '_check_answer', AsyncMock(side_effect=audit))
    monkeypatch.setattr(applier, '_emit_step', AsyncMock(side_effect=emit))
    monkeypatch.setattr(applier, '_wait_for_captcha', AsyncMock(return_value=False))
    result = await applier._drive(_job(), {}, '', '')
    assert result.error_category.value == 'captcha'
    agent.extract.assert_awaited_once()
    _assert_no_mutation(agent, native)


@pytest.mark.asyncio
@pytest.mark.parametrize('method,arguments', [('click', ()), ('fill', ('Facts',)), ('selectOption', ('Yes',)), ('check', ())])
async def test_native_executor_checks_provider_after_awaited_control_inspection(monkeypatch, method, arguments):
    applier, agent, native, _, monitor = _scenario(monkeypatch, [])
    role = 'checkbox' if method == 'check' else 'button'
    native.snapshot.return_value = SimpleNamespace(
        formatted_tree=f'[1] {role}: Current control', xpath_map={'1': 'observed-resume-control'})

    async def inspection():
        monitor.record('browserbase-solving-started')
        return False if method == 'check' else True

    if method == 'check': native.control.is_checked = AsyncMock(side_effect=inspection)
    else: native.control.is_visible = AsyncMock(side_effect=inspection)
    with pytest.raises(ActionDeferred):
        await GroundedAction('observed-resume-control', 'Current control', method, arguments).execute(
            native, before_mutation=lambda: applier._guard_verification(0))
    _assert_no_mutation(agent, native)


@pytest.mark.asyncio
async def test_upload_guard_checks_provider_after_file_input_count(monkeypatch):
    applier, agent, native, _, monitor = _scenario(monkeypatch, [])
    monkeypatch.setattr(mod, 'get_resume_bytes', lambda _: (b'%PDF-offline', '.pdf'))

    async def count():
        monitor.record('browserbase-solving-started')
        return 1

    native.file_input.count = AsyncMock(side_effect=count)
    with pytest.raises(ActionDeferred):
        await applier._upload_original(native)
    _assert_no_mutation(agent, native)


@pytest.mark.asyncio
async def test_verification_deferred_after_submit_intent_keeps_uncertainty_without_replay(monkeypatch):
    applier, agent, native, _, monitor = _scenario(monkeypatch, [
        _decision('upload'), dict(kind='submit', instruction='Submit application', reason='Reviewed')])
    claimed = False

    def claim(*args):
        nonlocal claimed
        claimed = True

    async def snapshot(**kwargs):
        if claimed: monitor.record('browserbase-solving-started')
        return SimpleNamespace(formatted_tree='[1] button: Submit application',
                               xpath_map={'1': 'observed-resume-control'})

    native.snapshot.side_effect = snapshot
    marker = MagicMock(side_effect=claim)
    monkeypatch.setattr(mod, 'mark_submission_intent', marker)
    monkeypatch.setattr(applier, '_upload_original', AsyncMock())
    monkeypatch.setattr(applier, '_check_answer', AsyncMock())
    result = await applier._drive(_job(), {}, '', '')
    assert result.error_category.value == 'submission_uncertain'
    marker.assert_called_once()
    assert agent.extract.await_count == 2
    _assert_no_mutation(agent, native)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['text', 'page', 'url', 'generation', 'active', 'receipt'])
@pytest.mark.parametrize('timing', ['during_model', 'during_wait'])
async def test_captcha_identity_change_requires_fresh_model_read(monkeypatch, change, timing):
    applier, agent, native, page, monitor = _scenario(monkeypatch, [_decision(), _decision('park')])

    def change_state():
        if change == 'text': native.snapshot.return_value.formatted_tree += '\n[3] textbox: Required answer'
        if change == 'page': native.page_id = 'another-application-tab'
        if change == 'url': page.url = URL + '?step=changed'
        if change == 'generation':
            monitor.record('browserbase-solving-started')
            monitor.record('browserbase-solving-finished')
        if change == 'active': monitor.record('browserbase-solving-started')
        if change == 'receipt': native.snapshot.return_value.formatted_tree = '[3] main: Your application has been submitted'

    extract = agent.extract.side_effect

    async def classify(*args, **kwargs):
        result = await extract(*args, **kwargs)
        if timing == 'during_model' and agent.extract.await_count == 1:
            change_state()
        return result

    waits = 0

    async def wait():
        nonlocal waits
        waits += 1
        if monitor.active:
            monitor.record('browserbase-solving-finished')
        elif timing == 'during_wait' and waits == 1:
            change_state()
        return True

    agent.extract.side_effect = classify
    monkeypatch.setattr(applier, '_wait_for_captcha', AsyncMock(side_effect=wait))
    with pytest.raises(ApplicationParked, match='Required factual answer'):
        await applier._drive(_job(), {}, '', '')
    assert agent.extract.await_count == 2
    assert all(call.kwargs['cache'] is False for call in agent.extract.await_args_list)
    _assert_no_mutation(agent, native)


@pytest.mark.asyncio
async def test_active_provider_owns_verification_until_idle_before_one_visual_read(monkeypatch):
    applier, agent, native, _, monitor = _scenario(monkeypatch, [_decision('park')])
    monitor.record('browserbase-solving-started')

    async def finish(**kwargs):
        agent.extract.assert_not_awaited()
        _assert_no_mutation(agent, native)
        monitor.record('browserbase-solving-finished')

    monitor.wait_until_idle = AsyncMock(side_effect=finish)
    with pytest.raises(ApplicationParked, match='Required factual answer'):
        await applier._drive(_job(), {}, '', '')
    agent.extract.assert_awaited_once()
    assert agent.extract.await_args.kwargs['cache'] is False
    assert agent.extract.await_args.kwargs['screenshot'] is True
    assert 'Hidden widgets or privacy badges alone' in agent.extract.await_args.args[0]
    assert not monitor.active
    _assert_no_mutation(agent, native)


@pytest.mark.asyncio
async def test_solver_start_during_native_read_yields_without_model_or_mutation(monkeypatch):
    applier, agent, native, _, monitor = _scenario(monkeypatch, [])

    async def snapshot(**kwargs):
        monitor.record('browserbase-solving-started')
        return SimpleNamespace(formatted_tree=CHALLENGE, xpath_map={})

    native.snapshot.side_effect = snapshot
    monkeypatch.setattr(applier, '_wait_for_captcha', AsyncMock(return_value=False))
    result = await applier._drive(_job(), {}, '', '')
    assert result.error_category.value == 'captcha'
    agent.extract.assert_not_awaited()
    _assert_no_mutation(agent, native)


@pytest.mark.asyncio
async def test_cached_verification_does_not_trigger_resume_upload_fast_path(monkeypatch):
    applier, agent, native, _, _ = _scenario(
        monkeypatch, [_decision()] * 10, url='https://smartapply.indeed.com/form/resume-selection')
    calls = 0

    async def wait():
        nonlocal calls
        calls += 1
        native.file_input.count.return_value = 1
        return calls < 3

    monkeypatch.setattr(applier, '_wait_for_captcha', AsyncMock(side_effect=wait))
    upload = AsyncMock()
    monkeypatch.setattr(applier, '_upload_original', upload)
    result = await applier._drive(_job(), {}, '', '')
    assert result.error_category.value == 'captcha'
    agent.extract.assert_awaited_once()
    upload.assert_not_awaited()
    _assert_no_mutation(agent, native)


@pytest.mark.asyncio
@pytest.mark.parametrize('active', [False, True])
async def test_verification_observation_cannot_authorize_loading_recovery(monkeypatch, active):
    applier, agent, native, _, monitor = _scenario(monkeypatch, [])
    if active: monitor.record('browserbase-solving-started')
    observation = await applier._read_page_observation(native, allow_verification=True)
    assert observation is not None
    assert observation.captcha_active is active
    assert await applier._read_loading_observation(native) is None
    assert not await applier._recover_loading_shell(native, observation)
    _assert_no_mutation(agent, native)


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', ['missing_page', 'empty_snapshot', 'receipt'])
async def test_unverifiable_native_state_never_caches_captcha_decision(monkeypatch, invalid):
    applier, agent, native, _, _ = _scenario(monkeypatch, [_decision(), _decision('park')])
    if invalid == 'missing_page': native.page_id = None
    if invalid == 'empty_snapshot': native.snapshot.return_value.formatted_tree = ''
    if invalid == 'receipt': native.snapshot.return_value.formatted_tree = '[1] main: Your application has been submitted'
    monkeypatch.setattr(applier, '_wait_for_captcha', AsyncMock(return_value=True))
    assert await applier._read_page_observation(native, allow_verification=True) is None
    with pytest.raises(ApplicationParked, match='Required factual answer'):
        await applier._drive(_job(), {}, '', '')
    assert agent.extract.await_count == 2
    _assert_no_mutation(agent, native)


@pytest.mark.asyncio
async def test_receipt_after_passive_wait_is_not_counted_as_a_new_submission(monkeypatch):
    applier, agent, native, _, _ = _scenario(monkeypatch, [_decision(), _decision('done')])

    async def receipt_appears():
        native.snapshot.return_value.formatted_tree = '[1] main: Your application has been submitted'
        return True

    monkeypatch.setattr(applier, '_wait_for_captcha', AsyncMock(side_effect=receipt_appears))
    result = await applier._drive(_job(), {}, '', '')
    assert result.status.value == 'skipped'
    assert not applier._submission_attempted
    assert agent.extract.await_count == 2
    _assert_no_mutation(agent, native)
