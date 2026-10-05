"""One bounded native GET can recover an observed pre-submit loading shell."""
import asyncio
from dataclasses import replace
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
# Gametime's recorded native AX adds a Go back button under generic ancestors,
# outside global navigation, while main contains only Preparing review. Adapt
# the existing sanitized shell; this is not a verbatim Stagehand snapshot.
GO_BACK_TREE = TREE.replace(
    '      [4-1779] div',
    '      [4-1779] div\n        [gametime-back] button: Go back',
)
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
    observation = await applier._read_loading_observation(native)
    return applier, native, agent, observation


@pytest.mark.asyncio
async def test_recorded_fuku_shell_allows_one_exact_get_never_reload(recovery):
    applier, page, _, observation = recovery
    assert await applier._recover_loading_shell(page, observation)
    page.goto.assert_awaited_once_with(URL, wait_until='domcontentloaded', timeout=30000)
    page.reload.assert_not_awaited()
    assert not await applier._recover_loading_shell(page, observation)
    assert page.goto.await_count == 1


@pytest.mark.asyncio
async def test_go_back_loading_shell_allows_one_guarded_get_without_clicking(recovery):
    applier, page, agent, _ = recovery
    page.snapshot.return_value.formatted_tree = GO_BACK_TREE
    observation = await applier._read_loading_observation(page)
    assert await applier._recover_loading_shell(page, observation)
    page.goto.assert_awaited_once_with(URL, wait_until='domcontentloaded', timeout=30000)
    assert not await applier._recover_loading_shell(page, observation)
    page.reload.assert_not_awaited()
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('condition', ['submitted', 'used', 'employer', 'short_deadline', 'captcha', 'different_tab', 'different_url', 'external_url'])
async def test_recovery_guards_do_not_navigate(recovery, condition):
    applier, page, agent, observation = recovery
    if condition == 'submitted': applier._submission_attempted = True
    if condition == 'used': applier._loading_recovery_used = True
    if condition == 'employer': applier.employer_site = True
    if condition == 'short_deadline': applier._application_deadline_at = asyncio.get_running_loop().time() + 100
    if condition == 'captcha': applier._captcha_monitor = SimpleNamespace(active=True, generation=1)
    if condition == 'different_tab': agent.browser.context.active_page.return_value = SimpleNamespace(page_id='other')
    if condition == 'different_url': page.url = AsyncMock(return_value=URL + '?different=draft')
    if condition == 'external_url': observation = replace(observation, url='https://employer.example/apply')
    assert not await applier._recover_loading_shell(page, observation)
    page.goto.assert_not_awaited(); page.reload.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('shell', [TREE, GO_BACK_TREE], ids=['original', 'go-back'])
@pytest.mark.parametrize('control', [
    '[x] button: Continue', '[x] focusable, button: Submit application', '[x] focusable,link: Continue', '[x] button: Submit application', '[x] textbox: City, state',
    '[x] combobox: Work authorization', '[x] select: Month', '[x] input: City', '[x] textarea: Summary', '[x] checkbox: I am not a robot',
    '[x] StaticText: Verify you are human', '[x] StaticText: Your application has been submitted',
])
async def test_form_challenge_or_receipt_change_invalidates_classified_wait(recovery, control, shell):
    applier, page, _, _ = recovery
    page.snapshot.return_value.formatted_tree = shell
    observation = await applier._read_loading_observation(page)
    page.snapshot.return_value.formatted_tree = shell + '\n' + control
    assert not await applier._recover_loading_shell(page, observation)
    page.goto.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['url', 'tab', 'captcha', 'submission'])
async def test_state_change_during_native_read_cancels_recovery(recovery, change):
    applier, page, agent, observation = recovery
    monitor = SimpleNamespace(active=False, generation=0); applier._captcha_monitor = monitor
    observation = replace(observation, captcha_generation=0)
    async def snapshot(**kwargs):
        if change == 'url': page.url = AsyncMock(return_value=URL + '?changed=1')
        if change == 'tab': agent.browser.context.active_page.return_value = SimpleNamespace(page_id='other')
        if change == 'captcha': monitor.generation += 1
        if change == 'submission': applier._submission_attempted = True
        return SimpleNamespace(formatted_tree=TREE)
    page.snapshot.side_effect = snapshot
    assert not await applier._recover_loading_shell(page, observation)
    page.goto.assert_not_awaited()


@pytest.mark.asyncio
async def test_navigation_timeout_consumes_only_recovery(recovery):
    applier, page, _, observation = recovery
    page.goto.side_effect = TimeoutError('ambiguous GET result')
    with pytest.raises(TimeoutError):
        await applier._recover_loading_shell(page, observation)
    assert not await applier._recover_loading_shell(page, observation)
    assert page.goto.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('shell', [TREE, GO_BACK_TREE], ids=['original', 'go-back'])
async def test_stalled_loop_recovers_once_reuploads_and_audits_before_submission(monkeypatch, shell):
    steps = ([dict(kind='upload', instruction='', reason='Attach original')] +
             [dict(kind='wait', instruction='', reason='Preparing review')] +
             [dict(kind='upload', instruction='', reason='Attach original again'),
              dict(kind='submit', instruction='Submit application', reason='Reviewed')])
    page = _page(URL); agent = _stagehand(page, steps)
    native = agent.browser.context.active_page.return_value
    native.page_id = 'observed-tab'; native.goto = AsyncMock(); native.reload = AsyncMock()
    native.snapshot.side_effect = None; native.snapshot.return_value = SimpleNamespace(formatted_tree=shell)
    async def form_loaded_after_recovery(*args, **kwargs):
        native.snapshot.return_value = SimpleNamespace(formatted_tree='[1] button: Edit resume')
    native.goto.side_effect = form_loaded_after_recovery
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
    assert 'uploaded in this application: False' in agent.extract.await_args_list[2].args[0]
    intent.assert_called_once(); action.execute.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('shell', [TREE, GO_BACK_TREE, TREE + '\n[x] button: Return to previous section'],
                         ids=['original', 'go-back', 'unfamiliar-control'])
async def test_second_sustained_stall_stops_instead_of_looping(monkeypatch, shell):
    page = _page(URL); agent = _stagehand(page, [dict(kind='wait',instruction='',reason='Loading')] * 14)
    native = agent.browser.context.active_page.return_value
    native.page_id = 'observed-tab'; native.goto = AsyncMock(); native.reload = AsyncMock()
    native.snapshot.side_effect = None; native.snapshot.return_value = SimpleNamespace(formatted_tree=shell)
    applier = IndeedApplier(page, 'offline', stagehand=agent)
    applier._application_deadline_at = asyncio.get_running_loop().time() + 700
    monkeypatch.setattr(mod.asyncio, 'sleep', AsyncMock());monkeypatch.setattr(applier, '_emit_step', AsyncMock())
    result = await applier._drive(_job(), {}, '', '')
    assert result.error_category.value == 'timeout'
    native.goto.assert_awaited_once();native.reload.assert_not_awaited()
    # One model classification per loading episode; native reads handle idle polls.
    assert agent.extract.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('new_state', [
    '[x] textbox: Work authorization', '[x] button: Continue',
    '[x] checkbox: I am not a robot', '[x] StaticText: Your application has been submitted',
])
async def test_native_loading_poll_replans_when_form_or_verification_changes(monkeypatch, new_state):
    page = _page(URL)
    agent = _stagehand(page, [dict(kind='wait', instruction='', reason='Loading'),
                             dict(kind='park', instruction='', reason='Required factual answer')])
    native = agent.browser.context.active_page.return_value
    native.page_id = 'observed-tab'
    native.snapshot.side_effect = None
    native.snapshot.return_value = SimpleNamespace(formatted_tree=TREE)
    async def state_changes_while_waiting(*args):
        native.snapshot.return_value = SimpleNamespace(formatted_tree=TREE + '\n' + new_state)
    applier = IndeedApplier(page, 'offline', stagehand=agent)
    monkeypatch.setattr(mod.asyncio, 'sleep', AsyncMock(side_effect=state_changes_while_waiting))
    monkeypatch.setattr(applier, '_emit_step', AsyncMock())
    monkeypatch.setattr(mod, 'resolve_application_question', AsyncMock(return_value=None))
    with pytest.raises(ApplicationParked, match='Required factual answer'):
        await applier._drive(_job(), {}, '', '')
    assert agent.extract.await_count == 2
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
async def test_solver_start_during_native_loading_poll_uses_managed_wait(monkeypatch):
    page = _page(URL)
    agent = _stagehand(page, [dict(kind='wait', instruction='', reason='Loading')])
    native = agent.browser.context.active_page.return_value
    native.page_id = 'observed-tab'
    monitor = SimpleNamespace(active=False, generation=0)
    agent._jobhunter_captcha_monitor = monitor
    reads = 0
    async def challenge_started(**kwargs):
        nonlocal reads
        reads += 1
        if reads >= 3:
            monitor.active = True
            monitor.generation += 1
        return SimpleNamespace(formatted_tree=TREE)
    native.snapshot.side_effect = challenge_started
    applier = IndeedApplier(page, 'offline', stagehand=agent)
    monkeypatch.setattr(mod.asyncio, 'sleep', AsyncMock())
    monkeypatch.setattr(applier, '_emit_step', AsyncMock())
    managed_wait = AsyncMock(return_value=False)
    monkeypatch.setattr(applier, '_wait_for_captcha', managed_wait)
    result = await applier._drive(_job(), {}, '', '')
    assert result.error_category.value == 'captcha'
    assert agent.extract.await_count == 1
    managed_wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_recovery_uses_installed_sdk_goto_contract(recovery):
    from stagehand.page import Page
    from stagehand._generated.models import PageRef, PageNavigationResult
    applier, page, _, observation = recovery
    ref = PageRef(page_id='observed-tab', url=URL)
    rpc = MagicMock()
    rpc.send = AsyncMock(return_value=PageNavigationResult(page=ref, response=None))
    page.goto = Page(rpc, ref).goto  # exercise actual SDK serialization, no provider transport
    assert await applier._recover_loading_shell(page, observation)
    method, params, _ = rpc.send.await_args.args
    assert method == 'page.goto'
    payload = params.model_dump(by_alias=True, mode='json', exclude_none=True)
    assert payload == {'page_id': 'observed-tab', 'url': URL,
                       'options': {'wait_until': 'domcontentloaded', 'timeout': 30000}}
    page.reload.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('receipt', mod.RECEIPT_PHRASES)
async def test_loading_next_to_any_recognized_receipt_cannot_authorize_wait(recovery, receipt):
    applier, page, _, _ = recovery
    page.snapshot.return_value.formatted_tree = TREE + '\n[x] StaticText: ' + receipt
    assert await applier._read_loading_observation(page) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', [None, {}, 'wait', 'page_id', 'url', 'fingerprint'])
async def test_missing_or_malformed_observation_never_navigates(recovery, invalid):
    applier, page, _, observation = recovery
    if isinstance(invalid, str) and invalid in {'page_id', 'url', 'fingerprint'}:
        invalid = replace(observation, **{invalid: None})
    assert not await applier._recover_loading_shell(page, invalid)
    page.goto.assert_not_awaited()


@pytest.mark.asyncio
async def test_fingerprint_ignores_node_ids_but_retains_all_native_snapshot_content(recovery):
    applier, page, _, observation = recovery
    page.snapshot.return_value.formatted_tree = TREE.replace('[4-', '[changed-')
    assert await applier._read_loading_observation(page) == observation
    for changed in [TREE.replace('Preparing review', 'Almost ready'),
                    TREE + '\n[x] textbox: City = San Francisco',
                    TREE + '\n[x] checked, checkbox: Work authorization',
                    TREE.replace('              [4-1988]', '                [4-1988]')]:
        page.snapshot.return_value.formatted_tree = changed
        assert await applier._read_loading_observation(page) != observation


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['input', 'receipt', 'challenge', 'page', 'url', 'captcha_generation'])
async def test_native_change_during_model_wait_requires_fresh_classification(monkeypatch, change):
    page = _page(URL)
    agent = _stagehand(page, [])
    native = agent.browser.context.active_page.return_value
    native.page_id = 'observed-tab'; native.goto = AsyncMock()
    native.snapshot.side_effect = None
    native.snapshot.return_value = SimpleNamespace(formatted_tree=GO_BACK_TREE)
    monitor = SimpleNamespace(active=False, generation=0)
    agent._jobhunter_captcha_monitor = monitor
    calls = 0
    async def classify(*args, **kwargs):
        nonlocal calls
        assert kwargs['cache'] is False
        calls += 1
        if calls == 1:
            additions = {'input': '[x] textbox: City',
                         'receipt': '[x] StaticText: Your application has been submitted',
                         'challenge': '[x] StaticText: Verify you are human'}
            if change in additions:
                native.snapshot.return_value.formatted_tree += '\n' + additions[change]
            if change == 'page': native.page_id = 'another-tab'
            if change == 'url': page.url = URL + '?new-step=1'
            if change == 'captcha_generation': monitor.generation += 1
        return SimpleNamespace(data=mod.NextStep(kind='wait' if calls == 1 else 'park',
                                               instruction='', reason='Fresh page decision'))
    agent.extract.side_effect = classify
    applier = IndeedApplier(page, 'offline', stagehand=agent)
    applier._application_deadline_at = asyncio.get_running_loop().time() + 700
    monkeypatch.setattr(mod.asyncio, 'sleep', AsyncMock())
    monkeypatch.setattr(applier, '_emit_step', AsyncMock())
    monkeypatch.setattr(mod, 'resolve_application_question', AsyncMock(return_value=None))
    with pytest.raises(ApplicationParked, match='Fresh page decision'):
        await applier._drive(_job(), {}, '', '')
    assert calls == 2
    native.goto.assert_not_awaited()
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
async def test_state_change_while_publishing_recovery_cancels_get(recovery):
    applier, page, _, observation = recovery
    async def changed_before_navigation(*args):
        page.snapshot.return_value.formatted_tree += '\n[x] button: Submit application'
    applier._emit_step.side_effect = changed_before_navigation
    assert not await applier._recover_loading_shell(page, observation)
    assert not await applier._recover_loading_shell(page, observation)
    page.goto.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('challenge', ['Verify you are human', 'Verifying you are human',
                                     'Confirm you are human', 'I am not a robot',
                                     'Security verification', 'Additional verification required',
                                     'Checking your browser'])
async def test_explicit_verification_cannot_authorize_a_loading_wait(recovery, challenge):
    applier, page, _, _ = recovery
    page.snapshot.return_value.formatted_tree = TREE + '\n[x] StaticText: ' + challenge
    assert await applier._read_loading_observation(page) is None
