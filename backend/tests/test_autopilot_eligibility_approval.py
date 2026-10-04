from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
@pytest.mark.parametrize('verdict', ['unknown', 'met'])
async def test_email_bulk_approval_requires_established_user_constraints(monkeypatch, verdict):
    from backend.gateway.routes import autopilot, sessions
    from backend.gateway import main
    monkeypatch.setattr('backend.shared.autopilot_store.complete_terminal_session', AsyncMock())
    monkeypatch.setattr(autopilot, 'verify_approval_token', lambda *args:True)
    monkeypatch.setattr(sessions, 'session_registry', {'s':{'status':'awaiting_review'}})
    graph=SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={
        'scored_jobs':[SimpleNamespace(eligibility_status=verdict)]})))
    monkeypatch.setattr(main, '_app_ref', SimpleNamespace(state=SimpleNamespace(graph=graph)))
    spawned=[]
    def spawn(coro):
        coro.close();spawned.append(True)
    monkeypatch.setattr(sessions, '_spawn_background', spawn)
    if verdict == 'unknown':
        with pytest.raises(HTTPException) as error:
            await autopilot.approve_autopilot_session('schedule', 's', token='fixture', action='approve')
        assert error.value.status_code == 409
        assert 'dashboard' in error.value.detail.lower()
        assert not spawned
    else:
        result=await autopilot.approve_autopilot_session('schedule', 's', token='fixture', action='approve')
        assert result['status']=='approved' and spawned==[True]


@pytest.mark.asyncio
async def test_confirmed_email_skip_releases_slot_after_durable_stop(monkeypatch):
    from backend.gateway.routes import autopilot, sessions
    from backend.shared import session_store
    monkeypatch.setattr('backend.shared.autopilot_store.complete_terminal_session', AsyncMock())
    monkeypatch.setattr(autopilot, 'verify_approval_token', lambda *args:True)
    monkeypatch.setattr(sessions, 'session_registry', {'s':{'status':'awaiting_review'}})
    order=[]
    monkeypatch.setattr(sessions, 'cancel_pipeline', AsyncMock(side_effect=lambda _:order.append('cancel')))
    monkeypatch.setattr(session_store, 'update_session_status', lambda *a, **kw:order.append('durable stop'))
    monkeypatch.setattr(sessions, '_release_task_slot', AsyncMock(side_effect=lambda _:order.append('release')))
    monkeypatch.setattr(sessions, 'unregister_emitter', lambda _:None)
    result=await autopilot.approve_autopilot_session('schedule','s',token='fixture',action='skip')
    assert result['status']=='skipped'
    assert sessions.session_registry['s']['status']=='failed'
    assert order == ['cancel','durable stop','release']


@pytest.mark.asyncio
async def test_failed_durable_email_skip_does_not_release_running_slot(monkeypatch):
    from backend.gateway.routes import autopilot, sessions
    from backend.shared import session_store
    monkeypatch.setattr('backend.shared.autopilot_store.complete_terminal_session', AsyncMock())
    monkeypatch.setattr(autopilot, 'verify_approval_token', lambda *args:True)
    monkeypatch.setattr(sessions, 'session_registry', {'s':{'status':'awaiting_review'}})
    monkeypatch.setattr(sessions, 'cancel_pipeline', AsyncMock())
    def fail(*args, **kwargs):raise RuntimeError('database unavailable')
    monkeypatch.setattr(session_store, 'update_session_status', fail)
    release=AsyncMock();monkeypatch.setattr(sessions, '_release_task_slot', release)
    with pytest.raises(RuntimeError):
        await autopilot.approve_autopilot_session('schedule','s',token='fixture',action='skip')
    release.assert_not_awaited()
