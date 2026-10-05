"""Offline cache regression: a cached plan never authorizes a stale browser target."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.browser.grounded_actions import UnresolvedControl, resolve_action
from backend.shared.application_rules import ApplicationParked
from backend.shared.config import settings


def _action(selector='/button[1]', *, method='click', arguments=()):
    return SimpleNamespace(selector=selector, method=method, arguments=list(arguments))


def _result(*actions, status='HIT'):
    return SimpleNamespace(data=list(actions), metadata=SimpleNamespace(
        cache=SimpleNamespace(status=status, count=2, threshold=1, tokens_saved=None)))


class Form:
    def __init__(self, label='Continue', role='button', *, credentials=False):
        self.controls = {'/button[1]': (role, label)}
        self.current_url = 'https://smartapply.indeed.com/form/questions'
        self.credentials = credentials
        self.native = {}
        self.snapshot = AsyncMock(side_effect=self._snapshot)
        self.url = AsyncMock(side_effect=lambda: self.current_url)
        self.locator = MagicMock(side_effect=self._locator)

    async def _snapshot(self, **_):
        return SimpleNamespace(
            formatted_tree='\n'.join(f'[1-{i}] {role}: {label}' for i, (role, label)
                                     in enumerate(self.controls.values(), 1)),
            xpath_map={f'1-{i}': selector for i, selector in enumerate(self.controls, 1)},
        )

    def _locator(self, selector):
        if 'password' in selector or 'one-time-code' in selector:
            return SimpleNamespace(count=AsyncMock(return_value=int(self.credentials)))
        if selector not in self.native:
            self.native[selector] = SimpleNamespace(
                count=AsyncMock(side_effect=lambda: int(selector in self.controls)),
                is_visible=AsyncMock(return_value=True),
                click=AsyncMock(), fill=AsyncMock(), select_option=AsyncMock(),
            )
        return self.native[selector]


@pytest.mark.asyncio
async def test_cache_hit_resolves_once_and_executes_with_fresh_native_validation():
    page = Form()
    agent = SimpleNamespace(observe=AsyncMock(return_value=_result(_action())), act=AsyncMock())
    action = await resolve_action(agent, page, 'Click Continue')
    assert agent.observe.await_args.kwargs.get('cache') is not False
    page._locator('/button[1]').click.assert_not_awaited()
    await action.execute(page)
    page._locator('/button[1]').click.assert_awaited_once()
    agent.observe.assert_awaited_once()
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
async def test_fresh_submission_resolution_bypasses_cache():
    page = Form('Submit application')
    agent = SimpleNamespace(observe=AsyncMock(return_value=_result(_action(), status='DISABLED')))
    action = await resolve_action(agent, page, 'Click Submit application', fresh=True)
    assert action.is_submission
    agent.observe.assert_awaited_once()
    assert agent.observe.await_args.kwargs['cache'] is False
    page._locator('/button[1]').click.assert_not_awaited()


@pytest.mark.asyncio
async def test_cached_action_disguising_submission_is_reobserved_without_cache():
    page = Form('Submit application')
    agent = SimpleNamespace(observe=AsyncMock(side_effect=[
        _result(_action()), _result(_action(), status='DISABLED')]))
    action = await resolve_action(agent, page, 'Click Continue')
    assert action.is_submission
    assert agent.observe.await_count == 2
    assert agent.observe.await_args.kwargs['cache'] is False
    page._locator('/button[1]').click.assert_not_awaited()


@pytest.mark.asyncio
async def test_control_changed_while_cache_was_read_requires_fresh_resolution():
    page = Form()
    calls = 0

    async def observe(*_, **__):
        nonlocal calls
        calls += 1
        if calls == 1:
            page.controls = {'/button[1]': ('button', 'Delete account'),
                             '/button[2]': ('button', 'Continue')}
            return _result(_action())
        return _result(_action('/button[2]'), status='DISABLED')

    agent = SimpleNamespace(observe=AsyncMock(side_effect=observe))
    action = await resolve_action(agent, page, 'Click Continue')
    assert agent.observe.await_args.kwargs['cache'] is False
    assert action.selector == '/button[2]'
    await action.execute(page)
    page._locator('/button[1]').click.assert_not_awaited()
    page._locator('/button[2]').click.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('cached', [
    _result(_action('/button[999]')),
    _result(_action(method='press', arguments=('Enter',))),
    _result(_action(), _action('/button[2]')),
])
async def test_unusable_cache_hit_falls_back_once_before_any_mutation(cached):
    page = Form()
    agent = SimpleNamespace(observe=AsyncMock(side_effect=[
        cached, _result(_action(), status='DISABLED')]))
    action = await resolve_action(agent, page, 'Click Continue')
    assert agent.observe.await_count == 2
    assert agent.observe.await_args.kwargs['cache'] is False
    page._locator('/button[1]').click.assert_not_awaited()
    await action.execute(page)
    page._locator('/button[1]').click.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_uncached_recovery_stops_without_browser_mutation():
    page = Form()
    invalid = _action(method='press', arguments=('Enter',))
    agent = SimpleNamespace(observe=AsyncMock(side_effect=[
        _result(invalid), _result(invalid, status='DISABLED')]))
    with pytest.raises(ApplicationParked):
        await resolve_action(agent, page, 'Click Continue')
    assert agent.observe.await_count == 2
    page._locator('/button[1]').click.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_model_result_is_not_retried_as_a_cache_failure():
    page = Form()
    agent = SimpleNamespace(observe=AsyncMock(return_value=_result(
        _action(method='press', arguments=('Enter',)), status='MISS')))
    with pytest.raises(ApplicationParked):
        await resolve_action(agent, page, 'Click Continue')
    agent.observe.assert_awaited_once()
    page._locator('/button[1]').click.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('method,arguments', [('click', ()), ('fill', ('Facts',)), ('check', ())])
@pytest.mark.parametrize('controls', [
    {},
    {'/button[1]': ('button', '')},
])
async def test_uncached_control_without_current_identity_requires_replanning(method, arguments, controls):
    page = Form()
    page.controls = controls
    agent = SimpleNamespace(observe=AsyncMock(return_value=_result(
        _action(method=method, arguments=arguments), status='MISS')))
    with pytest.raises(UnresolvedControl):
        await resolve_action(agent, page, 'Operate the observed control')
    # Resolution reports a technical mismatch; the caller owns bounded replanning.
    agent.observe.assert_awaited_once()
    page._locator('/button[1]').click.assert_not_awaited()
    page._locator('/button[1]').fill.assert_not_awaited()


@pytest.mark.asyncio
async def test_control_that_changes_again_during_uncached_retry_stops():
    page = Form()
    calls = 0

    async def observe(*_, **__):
        nonlocal calls
        calls += 1
        page.controls['/button[1]'] = ('button', f'Changed control {calls}')
        return _result(_action(), status='HIT' if calls == 1 else 'DISABLED')

    agent = SimpleNamespace(observe=AsyncMock(side_effect=observe))
    with pytest.raises(ApplicationParked):
        await resolve_action(agent, page, 'Click Continue')
    assert agent.observe.await_count == 2
    page._locator('/button[1]').click.assert_not_awaited()


@pytest.mark.asyncio
async def test_page_url_change_during_cache_lookup_requires_fresh_observation():
    page = Form()
    calls = 0

    async def observe(*_, **__):
        nonlocal calls
        calls += 1
        if calls == 1:
            page.current_url = 'https://smartapply.indeed.com/form/review'
        return _result(_action(), status='HIT' if calls == 1 else 'DISABLED')

    agent = SimpleNamespace(observe=AsyncMock(side_effect=observe))
    await resolve_action(agent, page, 'Click Continue')
    assert agent.observe.await_count == 2
    assert agent.observe.await_args.kwargs['cache'] is False


@pytest.mark.asyncio
async def test_credential_form_bypasses_cache_even_for_routine_instruction():
    page = Form(credentials=True)
    agent = SimpleNamespace(observe=AsyncMock(return_value=_result(_action(), status='DISABLED')))
    await resolve_action(agent, page, 'Click Continue')
    assert agent.observe.await_args.kwargs['cache'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('instruction', [
    'Fill the password field', 'Fill verification code 123456',
    'Enter the one-time code 123456', 'Fill the API key field',
])
async def test_credential_instruction_bypasses_cache_without_password_control(instruction):
    page = Form('Credential', 'textbox')
    agent = SimpleNamespace(observe=AsyncMock(return_value=_result(
        _action(method='fill', arguments=('fictional-value',)), status='DISABLED')))
    await resolve_action(agent, page, instruction)
    assert agent.observe.await_args.kwargs['cache'] is False
    page._locator('/button[1]').fill.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['/auth/login', '/signin', '/oauth/callback', '/account/verify'])
async def test_authentication_url_bypasses_cache_with_generic_instruction(path):
    page = Form()
    page.current_url = 'https://secure.indeed.com' + path
    agent = SimpleNamespace(observe=AsyncMock(return_value=_result(_action(), status='DISABLED')))
    await resolve_action(agent, page, 'Click Continue')
    assert agent.observe.await_args.kwargs['cache'] is False


@pytest.mark.asyncio
async def test_cache_kill_switch_preserves_native_execution_after_fresh_observation(monkeypatch):
    monkeypatch.setattr(settings, 'STAGEHAND_CACHE_ENABLED', False)
    page = Form()
    agent = SimpleNamespace(observe=AsyncMock(return_value=_result(_action(), status='DISABLED')))
    action = await resolve_action(agent, page, 'Click Continue')
    assert agent.observe.await_args.kwargs['cache'] is False
    await action.execute(page)
    page._locator('/button[1]').click.assert_awaited_once()


@pytest.mark.asyncio
async def test_target_changed_after_cache_resolution_still_cannot_execute():
    page = Form()
    agent = SimpleNamespace(observe=AsyncMock(return_value=_result(_action())))
    action = await resolve_action(agent, page, 'Click Continue')
    page.controls['/button[1]'] = ('button', 'Submit application')
    with pytest.raises(ApplicationParked):
        await action.execute(page)
    page._locator('/button[1]').click.assert_not_awaited()
