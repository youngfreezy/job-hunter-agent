"""Offline abuse case: a model classification must not authorize final submission."""
from types import SimpleNamespace

import pytest

from backend.tests.test_indeed_applier import _job, _page, _stagehand, _no_selector_db
from backend.browser.tools.appliers import indeed as indeed_mod
from backend.browser.tools.appliers.indeed import IndeedApplier


@pytest.mark.asyncio
async def test_stale_review_control_replans_before_audited_claimed_submit(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [dict(kind='upload', instruction='', reason=''),
                            dict(kind='act', instruction='Click Review your application', reason='Stale page'),
                            dict(kind='submit', instruction='Click Submit application', reason='Fresh review')])
    native = agent.browser.context.active_page.return_value
    native.snapshot.side_effect = None
    native.snapshot.return_value = SimpleNamespace(
        formatted_tree='[1-1] button: Submit application', xpath_map={'1-1':'/button[1]'})
    agent.observe.side_effect = [SimpleNamespace(data=[]), SimpleNamespace(data=[SimpleNamespace(
        method='click', selector='/button[1]', arguments=[])])]
    order = []
    marker = MagicMock(side_effect=lambda *_: order.append('claim'))
    monkeypatch.setattr(indeed_mod, 'mark_submission_intent', marker)
    native.control.click = AsyncMock(side_effect=lambda: order.append('submit'))
    applier = IndeedApplier(page, 'offline-audit', stagehand=agent)
    monkeypatch.setattr(applier, '_upload_original', AsyncMock())
    monkeypatch.setattr(applier, '_wait_for_receipt', AsyncMock(return_value=True))
    monkeypatch.setattr(applier, '_capture_screenshot', AsyncMock())
    audit = AsyncMock(side_effect=lambda *a, **k: order.append('audit'))
    monkeypatch.setattr(applier, '_check_answer', audit)
    result = await applier.run(job=_job(), user_profile={}, resume_text='Facts', cover_letter='')
    assert result.status.value == 'submitted'
    assert order == ['audit', 'claim', 'submit']
    assert audit.await_args.kwargs['review'] is True
    assert agent.extract.await_count == 3
    assert 'No browser action was executed' in agent.extract.await_args.args[0]
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,expected_reads', [('act', 2), ('submit', 1)])
async def test_unresolved_controls_are_technical_failures_not_personal_questions(monkeypatch, kind, expected_reads):
    from unittest.mock import AsyncMock
    page = _page('https://smartapply.indeed.com/form/review')
    decision = dict(kind=kind, instruction='Click Review application' if kind == 'act' else 'Click Submit application', reason='')
    agent = _stagehand(page, [dict(kind='upload', instruction='', reason=''), decision, decision])
    agent.observe.side_effect = None
    agent.observe.return_value = SimpleNamespace(data=[])
    applier = IndeedApplier(page, 'offline-audit', stagehand=agent)
    monkeypatch.setattr(applier, '_upload_original', AsyncMock())
    result = await applier.run(job=_job(), user_profile={}, resume_text='Facts', cover_letter='')
    assert result.status.value == 'failed'
    assert result.error_category.value == 'form_navigation'
    assert 'control' in result.error_message.lower()
    assert agent.observe.await_count == expected_reads
    agent.native_action.assert_not_awaited()
    indeed_mod.mark_submission_intent.assert_not_called()


@pytest.mark.asyncio
async def test_unresolved_control_after_submission_intent_never_replans(monkeypatch):
    from unittest.mock import AsyncMock
    from backend.browser.grounded_actions import UnresolvedControl
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [dict(kind='act', instruction='Click Continue', reason='')])
    agent.observe.side_effect = UnresolvedControl('No unique control')
    applier = IndeedApplier(page, 'offline-audit', stagehand=agent)
    applier._submission_attempted = True
    read = AsyncMock()
    monkeypatch.setattr(applier, '_visible_application_snapshot', read)
    result = await applier.apply(_job(), {}, 'Facts', '')
    assert result.error_category.value == 'submission_uncertain'
    assert 'check Indeed before retrying' in result.error_message
    agent.extract.assert_awaited_once()
    agent.observe.assert_awaited_once()
    read.assert_not_awaited()
    agent.native_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_misclassified_submit_cannot_run_without_resume_audit_and_durable_claim():
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [
        dict(kind='act', instruction='Click the Submit application button', reason='Continue'),
        dict(kind='done', instruction='', reason='Application completed'),
    ])
    agent.browser.context.active_page.return_value.snapshot.return_value = SimpleNamespace(
        formatted_tree='[1-1] button: Submit application', xpath_map={'1-1':'/button[1]'})
    agent.observe.side_effect = None
    agent.observe.return_value = SimpleNamespace(data=[SimpleNamespace(
        method='click', selector='/button[1]', arguments=[], description='Continue')])
    result = await IndeedApplier(page, 'offline-audit', stagehand=agent).run(
        job=_job(), user_profile={}, resume_text='Factual resume', cover_letter='')
    # Without the supplied file or a durable claim, even a misclassified final
    # click must stop before the browser mutation. The planner output is untrusted.
    agent.act.assert_not_awaited()
    agent.native_action.assert_not_awaited()
    assert 'resume' in result.error_message.lower()
    indeed_mod.mark_submission_intent.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('instruction', ['Click Submit application', 'Click Continue'])
async def test_observed_submit_target_requires_claim_and_review_even_for_act(monkeypatch, instruction):
    from unittest.mock import AsyncMock, MagicMock
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [dict(kind='upload',instruction='',reason=''),
                            dict(kind='act',instruction=instruction,reason='Next step')])
    native = agent.browser.context.active_page.return_value
    native.snapshot.side_effect = None
    native.snapshot.return_value = SimpleNamespace(
        formatted_tree='[1-1] button: Submit application', xpath_map={'1-1':'/button[1]'})
    agent.observe.side_effect = None
    agent.observe.return_value = SimpleNamespace(data=[SimpleNamespace(
        method='click',selector='/button[1]',arguments=[],description='Continue')])
    order=[]
    marker=MagicMock(side_effect=lambda *_: order.append('claim'))
    monkeypatch.setattr(indeed_mod, 'mark_submission_intent', marker)
    native.control.click = AsyncMock(side_effect=lambda: order.append('native click'))
    applier=IndeedApplier(page,'offline-audit',stagehand=agent)
    monkeypatch.setattr(applier,'_upload_original',AsyncMock())
    monkeypatch.setattr(applier,'_wait_for_receipt',AsyncMock(return_value=True))
    monkeypatch.setattr(applier,'_capture_screenshot',AsyncMock())
    audit=AsyncMock()
    monkeypatch.setattr(applier,'_check_answer',audit)
    result=await applier.run(job=_job(),user_profile={},resume_text='Facts',cover_letter='')
    assert result.status.value == 'submitted'
    assert order == ['claim','native click']
    assert audit.await_args.kwargs['review'] is True
    agent.act.assert_not_awaited()  # Session self-healing cannot reinterpret the target.


@pytest.mark.asyncio
async def test_native_executor_uses_sdk_locator_rpc_not_model_act():
    from unittest.mock import AsyncMock, MagicMock
    from stagehand.locator import Locator
    from backend.browser.grounded_actions import GroundedAction
    rpc=MagicMock()
    async def send(method, params, response_type):
        if method=='locator.count': return 1
        if method=='locator.is_visible': return True
        assert method=='locator.click'
    rpc.send=AsyncMock(side_effect=send)
    page=MagicMock()
    page.snapshot=AsyncMock(return_value=SimpleNamespace(
        formatted_tree='[1-1] button: Submit application',xpath_map={'1-1':'/button[1]'}))
    page.locator=lambda selector: Locator(rpc,page_id='fixture',selector=selector)
    await GroundedAction('/button[1]','Submit application','click',()).execute(page)
    assert [call.args[0] for call in rpc.send.await_args_list] == [
        'locator.count','locator.is_visible','locator.click']


@pytest.mark.asyncio
async def test_changed_observed_target_cannot_self_heal_to_submit():
    from unittest.mock import AsyncMock, MagicMock
    from backend.browser.grounded_actions import GroundedAction
    from backend.shared.application_rules import ApplicationParked
    page=MagicMock()
    page.snapshot=AsyncMock(return_value=SimpleNamespace(
        formatted_tree='[1-1] button: Submit application',xpath_map={'1-1':'/button[1]'}))
    with pytest.raises(ApplicationParked):
        await GroundedAction('/button[1]','Continue','click',()).execute(page)
    page.locator.assert_not_called()


@pytest.mark.asyncio
async def test_target_change_after_claim_preserves_uncertain_hold(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from backend.shared.models.schemas import ApplicationErrorCategory
    page = _page('https://smartapply.indeed.com/form/review')
    agent = _stagehand(page, [dict(kind='upload', instruction='', reason=''),
                            dict(kind='act', instruction='Click Submit application', reason='Ready')])
    native = agent.browser.context.active_page.return_value
    claimed = False
    def claim(*_):
        nonlocal claimed
        claimed = True
    monkeypatch.setattr(indeed_mod, 'mark_submission_intent', MagicMock(side_effect=claim))
    async def snapshot(**_):
        label = 'Changed control' if claimed else 'Submit application'
        return SimpleNamespace(formatted_tree=f'[1-1] button: {label}',
                               xpath_map={'1-1': 'observed-resume-control'})
    native.snapshot.side_effect = snapshot
    applier = IndeedApplier(page, 'offline-audit', stagehand=agent)
    monkeypatch.setattr(applier, '_upload_original', AsyncMock())
    result = await applier.run(job=_job(), user_profile={}, resume_text='Facts', cover_letter='')
    assert claimed
    assert result.error_category == ApplicationErrorCategory.SUBMISSION_UNCERTAIN
    agent.native_action.assert_not_awaited()
    agent.act.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('method,arguments', [('press', ['Enter']), ('click', ['javascript:submit()'])])
async def test_unsupported_observed_mutations_never_execute(method, arguments):
    from unittest.mock import AsyncMock, MagicMock
    from backend.browser.grounded_actions import resolve_action
    from backend.shared.application_rules import ApplicationParked
    agent = MagicMock()
    agent.observe = AsyncMock(return_value=SimpleNamespace(data=[SimpleNamespace(
        method=method, arguments=arguments, selector='/button[1]')]))
    page = MagicMock()
    with pytest.raises(ApplicationParked):
        await resolve_action(agent, page, 'Continue')
    page.locator.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('method,initial,expected', [('check', False, True), ('check', True, True),
                                                   ('uncheck', True, False), ('uncheck', False, False)])
async def test_checkbox_native_action_is_idempotent(method, initial, expected):
    from unittest.mock import AsyncMock, MagicMock
    from stagehand.locator import Locator
    from backend.browser.grounded_actions import resolve_action
    checked = initial
    async def send(method, params, response_type):
        nonlocal checked
        if method == 'locator.count': return 1
        if method == 'locator.is_visible': return True
        if method == 'locator.is_checked': return checked
        assert method == 'locator.click'
        checked = not checked
    rpc = MagicMock(send=AsyncMock(side_effect=send))
    page = MagicMock()
    page.snapshot = AsyncMock(return_value=SimpleNamespace(
        formatted_tree='[1-1] checkbox: I acknowledge the privacy notice',
        xpath_map={'1-1': '/input[1]'}))
    page.locator = lambda selector: Locator(rpc, page_id='fixture', selector=selector)
    agent = MagicMock(observe=AsyncMock(return_value=SimpleNamespace(data=[SimpleNamespace(
        method=method, arguments=[], selector='/input[1]')])) )
    action = await resolve_action(agent, page, 'Set the privacy acknowledgement')
    await action.execute(page)
    assert checked == expected
    assert sum(call.args[0] == 'locator.click' for call in rpc.send.await_args_list) == (initial != expected)


@pytest.mark.asyncio
async def test_check_cannot_disguise_a_submit_button():
    from unittest.mock import AsyncMock, MagicMock
    from backend.browser.grounded_actions import resolve_action
    from backend.shared.application_rules import ApplicationParked
    agent = MagicMock(observe=AsyncMock(return_value=SimpleNamespace(data=[SimpleNamespace(
        method='check', arguments=[], selector='/button[1]')])) )
    page = MagicMock(snapshot=AsyncMock(return_value=SimpleNamespace(
        formatted_tree='[1-1] button: Submit application', xpath_map={'1-1': '/button[1]'})))
    with pytest.raises(ApplicationParked):
        await resolve_action(agent, page, 'Acknowledge')
    page.locator.assert_not_called()
