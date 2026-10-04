"""One bounded native GET can recover an observed pre-submit loading shell."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from backend.browser.tools.appliers import indeed as mod
from backend.browser.tools.appliers.indeed import IndeedApplier
from backend.shared.application_rules import ApplicationParked
from backend.tests.test_indeed_applier import _job, _page, _stagehand

TREE = (Path(__file__).parent / 'fixtures/indeed_loading_shell.txt').read_text()
URL = 'https://smartapply.indeed.com/beta/indeedapply/form/review'


@pytest_asyncio.fixture
async def recovery(monkeypatch):
    page = _page(URL)
    agent = _stagehand(page, [])
    native = agent.browser.context.active_page.return_value
    native.page_id = 'observed-tab'
    native.snapshot.side_effect = None
    native.snapshot.return_value = SimpleNamespace(formatted_tree=TREE)
    native.goto = AsyncMock()
    native.reload = AsyncMock(side_effect=AssertionError('POST-replaying reload is forbidden'))
    applier = IndeedApplier(page, 'offline', stagehand=agent)
    applier._application_deadline_at = asyncio.get_running_loop().time() + 700
    monkeypatch.setattr(applier, '_emit_step', AsyncMock())
    return applier, native, agent


@pytest.mark.asyncio
async def test_recorded_fuku_shell_allows_one_exact_get_never_reload(recovery):
    applier, page, _ = recovery
    assert await applier._recover_loading_shell(page, URL, page.page_id)
    page.goto.assert_awaited_once_with(URL, wait_until='domcontentloaded', timeout=30000)
    page.reload.assert_not_awaited()
    assert not await applier._recover_loading_shell(page, URL, page.page_id)
    assert page.goto.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('condition', ['submitted', 'used', 'employer', 'short_deadline', 'captcha', 'different_tab', 'different_url', 'external_url'])
async def test_recovery_guards_do_not_navigate(recovery, condition):
    applier, page, agent = recovery
    expected = URL
    if condition == 'submitted': applier._submission_attempted = True
    if condition == 'used': applier._loading_recovery_used = True
    if condition == 'employer': applier.employer_site = True
    if condition == 'short_deadline': applier._application_deadline_at = asyncio.get_running_loop().time() + 100
    if condition == 'captcha': applier._captcha_monitor = SimpleNamespace(active=True, generation=1)
    if condition == 'different_tab': agent.browser.context.active_page.return_value = SimpleNamespace(page_id='other')
    if condition == 'different_url': page.url = AsyncMock(return_value=URL + '?different=draft')
    if condition == 'external_url': expected = 'https://employer.example/apply'
    assert not await applier._recover_loading_shell(page, expected, 'observed-tab')
    page.goto.assert_not_awaited(); page.reload.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('control', [
    '[x] button: Continue', '[x] focusable, button: Submit application', '[x] focusable,link: Continue', '[x] button: Submit application', '[x] textbox: City, state',
    '[x] combobox: Work authorization', '[x] select: Month', '[x] input: City', '[x] textarea: Summary', '[x] checkbox: I am not a robot',
    '[x] StaticText: Verify you are human', '[x] StaticText: Your application has been submitted',
])
async def test_actionable_form_challenge_or_receipt_is_not_loading_only(recovery, control):
    applier, page, _ = recovery
    page.snapshot.return_value.formatted_tree = TREE + '\n' + control
    assert not await applier._recover_loading_shell(page, URL, page.page_id)
    page.goto.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['url', 'tab', 'captcha', 'submission'])
async def test_state_change_during_native_read_cancels_recovery(recovery, change):
    applier, page, agent = recovery
    monitor = SimpleNamespace(active=False, generation=0); applier._captcha_monitor = monitor
    async def snapshot(**kwargs):
        if change == 'url': page.url = AsyncMock(return_value=URL + '?changed=1')
        if change == 'tab': agent.browser.context.active_page.return_value = SimpleNamespace(page_id='other')
        if change == 'captcha': monitor.generation += 1
        if change == 'submission': applier._submission_attempted = True
        return SimpleNamespace(formatted_tree=TREE)
    page.snapshot.side_effect = snapshot
    assert not await applier._recover_loading_shell(page, URL, 'observed-tab')
    page.goto.assert_not_awaited()


@pytest.mark.asyncio
async def test_navigation_timeout_consumes_only_recovery(recovery):
    applier, page, _ = recovery
    page.goto.side_effect = TimeoutError('ambiguous GET result')
    with pytest.raises(TimeoutError):
        await applier._recover_loading_shell(page, URL, 'observed-tab')
    assert not await applier._recover_loading_shell(page, URL, 'observed-tab')
    assert page.goto.await_count == 1


@pytest.mark.asyncio
async def test_stalled_loop_recovers_once_reuploads_and_audits_before_submission(monkeypatch):
    steps = ([dict(kind='upload', instruction='', reason='Attach original')] +
             [dict(kind='wait', instruction='', reason='Preparing review')] * 7 +
             [dict(kind='upload', instruction='', reason='Attach original again'),
              dict(kind='submit', instruction='Submit application', reason='Reviewed')])
    page = _page(URL); agent = _stagehand(page, steps)
    native = agent.browser.context.active_page.return_value
    native.page_id = 'observed-tab'; native.goto = AsyncMock(); native.reload = AsyncMock()
    native.snapshot.side_effect = None; native.snapshot.return_value = SimpleNamespace(formatted_tree=TREE)
    applier = IndeedApplier(page, 'offline', stagehand=agent)
    applier._application_deadline_at = asyncio.get_running_loop().time() + 700
    monkeypatch.setattr(mod.asyncio, 'sleep', AsyncMock())
    monkeypatch.setattr(applier, '_emit_step', AsyncMock())
    upload = AsyncMock(); monkeypatch.setattr(applier, '_upload_original', upload)
    audit = AsyncMock(); monkeypatch.setattr(applier, '_check_answer', audit)
    monkeypatch.setattr(applier, '_wait_for_receipt', AsyncMock(return_value=True))
    monkeypatch.setattr(applier, '_capture_screenshot', AsyncMock())
    action = MagicMock(is_submission=True, execute=AsyncMock(), audit_text=lambda:'Submit application')
    monkeypatch.setattr(mod, 'resolve_action', AsyncMock(return_value=action))
    def claim(*args):
        assert upload.await_count == 2
        audit.assert_awaited_once()
        assert audit.await_args.kwargs['review'] is True
    intent = MagicMock(side_effect=claim); monkeypatch.setattr(mod, 'mark_submission_intent', intent)
    result = await applier._drive(_job(), {}, 'canonical', '')
    assert result.status.value == 'submitted'
    assert upload.await_count == 2; native.goto.assert_awaited_once(); native.reload.assert_not_awaited()
    assert 'uploaded in this application: False' in agent.extract.await_args_list[8].args[0]
    intent.assert_called_once(); action.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_second_sustained_stall_stops_instead_of_looping(monkeypatch):
    page = _page(URL); agent = _stagehand(page, [dict(kind='wait',instruction='',reason='Loading')] * 14)
    native = agent.browser.context.active_page.return_value
    native.page_id = 'observed-tab'; native.goto = AsyncMock(); native.reload = AsyncMock()
    native.snapshot.side_effect = None; native.snapshot.return_value = SimpleNamespace(formatted_tree=TREE)
    applier = IndeedApplier(page, 'offline', stagehand=agent)
    applier._application_deadline_at = asyncio.get_running_loop().time() + 700
    monkeypatch.setattr(mod.asyncio, 'sleep', AsyncMock());monkeypatch.setattr(applier, '_emit_step', AsyncMock())
    result = await applier._drive(_job(), {}, '', '')
    assert result.error_category.value == 'timeout'
    native.goto.assert_awaited_once();native.reload.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_uses_installed_sdk_goto_contract(recovery):
    from stagehand.page import Page
    from stagehand._generated.models import PageRef, PageNavigationResult
    applier, page, _ = recovery
    ref = PageRef(page_id='observed-tab', url=URL)
    rpc = MagicMock()
    rpc.send = AsyncMock(return_value=PageNavigationResult(page=ref, response=None))
    page.goto = Page(rpc, ref).goto  # exercise actual SDK serialization, no provider transport
    assert await applier._recover_loading_shell(page, URL, 'observed-tab')
    method, params, _ = rpc.send.await_args.args
    assert method == 'page.goto'
    payload = params.model_dump(by_alias=True, mode='json', exclude_none=True)
    assert payload == {'page_id': 'observed-tab', 'url': URL,
                       'options': {'wait_until': 'domcontentloaded', 'timeout': 30000}}
    page.reload.assert_not_awaited()


@pytest.mark.parametrize('receipt', mod.RECEIPT_PHRASES)
def test_loading_next_to_any_recognized_receipt_never_recovers(receipt):
    assert not IndeedApplier._loading_only_snapshot(TREE + '\n[x] StaticText: ' + receipt)


def test_qualified_global_navigation_keeps_actual_loading_fixture_usable():
    assert IndeedApplier._loading_only_snapshot(TREE.replace('navigation: Primary', 'focusable,navigation: Primary'))
