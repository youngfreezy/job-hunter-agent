"""Inspection can reveal a lower viewport, but never operate an application control."""
import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.browser.tools.appliers import indeed as mod
from backend.shared.application_rules import ApplicationParked
from backend.shared.model_budget import BudgetStopped
from backend.browser import verification_inspection as inspection
from backend.tests.test_indeed_applier import _job
from backend.tests.test_indeed_captcha_polling import _scenario, _decision


def _scroll_action(method='scrollTo', arguments=('100%',), selector='observed-scroll-container'):
    return SimpleNamespace(method=method, arguments=list(arguments), selector=selector)


def _inspection(monkeypatch):
    applier, agent, page, host_page, monitor = _scenario(monkeypatch, [])
    agent.observe.side_effect = None
    agent.observe.return_value = SimpleNamespace(data=[_scroll_action()])
    agent.extract = AsyncMock(return_value=SimpleNamespace(data=mod.NextStep(**_decision())))
    page.control.scroll_to = AsyncMock()
    page.evaluate = AsyncMock(return_value=True)
    return applier, agent, page, host_page, monitor


async def _inspect(applier, agent, page, *, deadline=None):
    return await inspection.inspect_verification_view(
        agent, page, prompt='Current application policy and supplied facts.', schema=mod.NextStep,
        expected_url='https://smartapply.indeed.com/form/review',
        guard=lambda: applier._guard_verification(0),
        deadline=deadline if deadline is not None else asyncio.get_running_loop().time() + 60,
    )


@pytest.mark.asyncio
async def test_inconclusive_finished_solver_view_gets_one_scroll_only_visual_inspection(monkeypatch):
    applier, agent, page, _, monitor = _scenario(monkeypatch, [_decision(), _decision('park')])
    monitor.record('browserbase-solving-started')
    monitor.record('browserbase-solving-finished')
    agent.observe.side_effect = None
    agent.observe.return_value = SimpleNamespace(data=[_scroll_action()])
    page.control.scroll_to = AsyncMock()
    page.evaluate = AsyncMock(return_value=True)
    monkeypatch.setattr(applier, '_wait_for_captcha', AsyncMock(return_value=False))
    with pytest.raises(ApplicationParked, match='Required factual answer'):
        await applier._drive(_job(), {}, '', '')
    agent.observe.assert_awaited_once()
    assert agent.observe.await_args.kwargs['cache'] is False
    page.control.scroll_to.assert_awaited_once_with(100)
    assert agent.extract.await_count == 2
    assert all(call.kwargs.get('screenshot') is True and call.kwargs['cache'] is False
               for call in agent.extract.await_args_list)
    agent.native_action.assert_not_awaited()
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
async def test_verification_timeout_persists_owned_full_page_screenshot(monkeypatch):
    applier, _, page, _, _ = _scenario(monkeypatch, [_decision()])
    applier.page.screenshot = AsyncMock(return_value=b'full-page-png')
    store = MagicMock(return_value='stored-proof')
    monkeypatch.setattr('backend.shared.screenshot_store.store_screenshot_bytes', store)
    monkeypatch.setattr(applier, '_wait_for_captcha', AsyncMock(return_value=False))
    job = _job()
    result = await applier._drive(job, {}, '', '')
    assert result.error_category.value == 'captcha'
    assert result.screenshot_url == '/api/sessions/offline-captcha/screenshots/stored-proof'
    applier.page.screenshot.assert_awaited_once()
    assert applier.page.screenshot.await_args.kwargs['full_page'] is True
    store.assert_called_once_with(session_id='offline-captcha', job_id=str(job.id), image_data=b'full-page-png')


@pytest.mark.asyncio
@pytest.mark.parametrize('argument', ['100', '100%', 100])
async def test_only_observed_bottom_scroll_precedes_fresh_visual_read(monkeypatch, argument):
    applier, agent, page, _, _ = _inspection(monkeypatch)
    agent.observe.return_value.data = [_scroll_action(arguments=(argument,))]
    result = await _inspect(applier, agent, page)
    assert result is agent.extract.return_value
    agent.observe.assert_awaited_once()
    assert agent.observe.await_args.kwargs['cache'] is False
    page.control.scroll_to.assert_awaited_once_with(100)
    page.evaluate.assert_awaited_once_with(inspection.SCROLL_QUIET_SCRIPT)
    assert agent.extract.await_args.kwargs['screenshot'] is True
    assert agent.extract.await_args.kwargs['cache'] is False
    agent.act.assert_not_awaited()
    agent.native_action.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('actions', [
    [], [_scroll_action(), _scroll_action()], [_scroll_action(method='click')],
    [_scroll_action(method='fill')], [_scroll_action(method='press', arguments=('End',))],
    [_scroll_action(arguments=())], [_scroll_action(arguments=('50%',))],
    [_scroll_action(arguments=('-100%',))], [_scroll_action(arguments=('100%', 'click'))],
    [_scroll_action(selector='')], [_scroll_action(selector=None)],
])
async def test_invalid_inspection_never_falls_back_to_click_or_model_act(monkeypatch, actions):
    applier, agent, page, _, _ = _inspection(monkeypatch)
    agent.observe.return_value.data = actions
    assert await _inspect(applier, agent, page) is None
    page.control.scroll_to.assert_not_awaited()
    agent.extract.assert_not_awaited()
    agent.act.assert_not_awaited()
    agent.native_action.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('count,visible', [(0, True), (2, True), (1, False)])
async def test_ambiguous_or_invisible_container_never_scrolls(monkeypatch, count, visible):
    applier, agent, page, _, _ = _inspection(monkeypatch)
    page.control.count.return_value = count
    page.control.is_visible.return_value = visible
    assert await _inspect(applier, agent, page) is None
    page.control.scroll_to.assert_not_awaited()
    agent.extract.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['active', 'generation', 'page', 'url'])
@pytest.mark.parametrize('boundary', ['observe', 'visibility', 'scroll', 'visual'])
async def test_identity_change_stops_inspection_at_each_await_boundary(monkeypatch, change, boundary):
    applier, agent, page, host_page, monitor = _inspection(monkeypatch)

    def changed():
        if change == 'active': monitor.record('browserbase-solving-started')
        if change == 'generation':
            monitor.record('browserbase-solving-started')
            monitor.record('browserbase-solving-finished')
        if change == 'page': page.page_id = 'different-tab'
        if change == 'url': host_page.url += '?new-step=1'

    async def operation(*args, **kwargs):
        changed()
        return {'observe': agent.observe.return_value, 'visibility': True,
                'scroll': None, 'visual': agent.extract.return_value}[boundary]

    target = {'observe': agent.observe, 'visibility': page.control.is_visible,
              'scroll': page.control.scroll_to, 'visual': agent.extract}[boundary]
    target.side_effect = operation
    assert await _inspect(applier, agent, page) is None
    if boundary in ('observe', 'visibility'): page.control.scroll_to.assert_not_awaited()
    if boundary != 'visual': agent.extract.assert_not_awaited()
    agent.act.assert_not_awaited()
    agent.native_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_or_expired_inspection_makes_no_model_request(monkeypatch):
    applier, agent, page, _, monitor = _inspection(monkeypatch)
    assert await _inspect(applier, agent, page, deadline=asyncio.get_running_loop().time() - 1) is None
    monitor.record('browserbase-solving-started')
    assert await _inspect(applier, agent, page) is None
    agent.observe.assert_not_awaited()
    agent.extract.assert_not_awaited()
    page.control.scroll_to.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [BudgetStopped('Model spend ceiling reached; paid request blocked.'), asyncio.CancelledError()])
@pytest.mark.parametrize('boundary', ['observe', 'visual'])
async def test_budget_stops_and_cancellation_propagate_without_fallback(monkeypatch, failure, boundary):
    applier, agent, page, _, _ = _inspection(monkeypatch)
    getattr(agent, boundary if boundary == 'observe' else 'extract').side_effect = failure
    with pytest.raises(type(failure)):
        await _inspect(applier, agent, page)
    if boundary == 'observe':
        page.control.scroll_to.assert_not_awaited()
        agent.extract.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary', ['observe', 'visual'])
async def test_inspection_timeout_is_bounded_and_does_not_retry(monkeypatch, boundary):
    applier, agent, page, _, _ = _inspection(monkeypatch)

    async def pending(*args, **kwargs):
        await asyncio.Event().wait()

    operation = agent.observe if boundary == 'observe' else agent.extract
    operation.side_effect = pending
    assert await _inspect(applier, agent, page, deadline=asyncio.get_running_loop().time() + 0.01) is None
    operation.assert_awaited_once()
    if boundary == 'observe': page.control.scroll_to.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsettled_scroll_does_not_spend_on_another_visual_read(monkeypatch):
    applier, agent, page, _, _ = _inspection(monkeypatch)
    page.evaluate.return_value = False
    assert await _inspect(applier, agent, page) is None
    page.control.scroll_to.assert_awaited_once()
    agent.extract.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_inspection_is_not_repeated_for_a_new_solver_generation(monkeypatch):
    applier, agent, page, _, monitor = _scenario(monkeypatch, [_decision(), _decision(), _decision('park')])
    monitor.record('browserbase-solving-started')
    monitor.record('browserbase-solving-finished')
    inspect = AsyncMock(return_value=None)
    monkeypatch.setattr(mod, 'inspect_verification_view', inspect)
    waits = 0
    deadlines = []

    async def wait():
        nonlocal waits
        waits += 1
        deadlines.append(applier._captcha_deadline_at)
        if waits == 1:
            monitor.record('browserbase-solving-started')
            monitor.record('browserbase-solving-finished')
        return True

    monkeypatch.setattr(applier, '_wait_for_captcha', AsyncMock(side_effect=wait))
    with pytest.raises(ApplicationParked, match='Required factual answer'):
        await applier._drive(_job(), {}, '', '')
    inspect.assert_awaited_once()
    assert len(set(deadlines)) == 1
    assert inspect.await_args.kwargs['deadline'] == deadlines[0]
    assert applier._verification_inspection_used


@pytest.mark.asyncio
async def test_timeout_diagnostic_is_bounded_and_cannot_suppress_cancellation(monkeypatch):
    monkeypatch.setattr(inspection, 'DIAGNOSTIC_TIMEOUT_SECONDS', 0.01)

    async def pending():
        await asyncio.Event().wait()

    await inspection.capture_verification_timeout(pending)
    with pytest.raises(asyncio.CancelledError):
        await inspection.capture_verification_timeout(AsyncMock(side_effect=asyncio.CancelledError()))


@pytest.mark.asyncio
@pytest.mark.parametrize('stop', ['timeout', 'cancel'])
async def test_blocked_screenshot_store_does_not_block_loop_or_diagnostic_stop(monkeypatch, stop):
    applier, _, _, _, _ = _scenario(monkeypatch, [])
    applier.page.screenshot = AsyncMock(return_value=b'owned-png')
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    loop_thread = threading.get_ident()
    worker_threads = []
    stored_arguments = []

    def blocked_store(**kwargs):
        worker_threads.append(threading.get_ident())
        stored_arguments.append(kwargs)
        entered.set()
        try:
            release.wait(timeout=2)
            return 'late-proof'
        finally:
            finished.set()

    monkeypatch.setattr('backend.shared.screenshot_store.store_screenshot_bytes', blocked_store)
    monkeypatch.setattr(inspection, 'DIAGNOSTIC_TIMEOUT_SECONDS', 0.02 if stop == 'timeout' else 1)
    job = _job()
    capture = asyncio.create_task(inspection.capture_verification_timeout(lambda: applier._capture_screenshot(job)))
    try:
        while not entered.is_set():
            await asyncio.sleep(0.001)
        assert len(worker_threads) == 1 and worker_threads[0] != loop_thread
        assert not finished.is_set()  # Event loop resumed while the database is still blocked.
        if stop == 'cancel':
            capture.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(capture, timeout=0.2)
        else:
            await asyncio.wait_for(capture, timeout=0.2)
        assert not release.is_set() and not finished.is_set()
        assert applier._screenshot_path is None
        assert stored_arguments == [{'session_id': 'offline-captcha', 'job_id': str(job.id), 'image_data': b'owned-png'}]
    finally:
        release.set()
        await asyncio.to_thread(finished.wait, 1)
        if not capture.done():
            capture.cancel()
            with pytest.raises(asyncio.CancelledError):
                await capture
