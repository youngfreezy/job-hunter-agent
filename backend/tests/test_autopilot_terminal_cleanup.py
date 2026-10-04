"""Terminal cleanup survives process restarts without resuming recurrence or jobs."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import pytest

from backend.shared import autopilot_store as store, session_store
from backend.shared.config import settings
from backend.gateway.routes import sessions, autopilot


@pytest.fixture
def recovered(monkeypatch):
    row = {'status':'awaiting_review','user_id':'owner'}
    monkeypatch.setattr(sessions, 'session_registry', {})
    monkeypatch.setattr('backend.gateway.deps.get_current_user', lambda _: {'id':'owner'})
    monkeypatch.setattr(session_store, 'get_session_by_id', lambda _: row)
    monkeypatch.setattr(sessions, 'is_pipeline_active', lambda _: False)
    monkeypatch.setattr(sessions, 'cancel_pipeline', AsyncMock())
    monkeypatch.setattr(sessions, 'unregister_emitter', lambda _: None)
    order = []
    def stop(sid,status,**kw):
        assert kw['raise_on_error']
        row['status'] = status
        order.append('terminal')
    monkeypatch.setattr(session_store, 'update_session_status', stop)
    async def cleanup(sid):
        assert row['status'] in ('failed','completed')
        order.append('schedule')
    monkeypatch.setattr(store, 'complete_terminal_session', cleanup, raising=False)
    monkeypatch.setattr(sessions, '_release_task_slot', AsyncMock(side_effect=lambda _:order.append('slot')))
    monkeypatch.setattr(autopilot, 'verify_approval_token', lambda *args:True)
    return row,order


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['dashboard','email'])
async def test_recovered_stop_clears_schedule_after_durable_terminal_write(recovered, entry):
    row,order = recovered
    if entry == 'dashboard':
        await sessions.kill_session('recovered',object())
    else:
        await autopilot.approve_autopilot_session('schedule','recovered',token='signed',action='skip')
    assert order == ['terminal','schedule','slot']


@pytest.mark.asyncio
async def test_repeated_kill_repairs_previously_stale_schedule(recovered):
    row,order = recovered
    row['status']='completed'
    assert await sessions.kill_session('recovered',object()) == {'status':'already_done'}
    assert order == ['schedule','slot']


@pytest.fixture
def isolated_store(monkeypatch):
    if urlsplit(settings.DATABASE_URL).hostname not in ('localhost','127.0.0.1','::1'):
        pytest.fail('Terminal cleanup tests require local PostgreSQL; refusing remote DB.')
    schema = 'terminal_test_' + uuid4().hex
    with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA {schema}')
    @contextmanager
    def connect():
        with psycopg.connect(settings.DATABASE_URL, options=f'-c search_path={schema}') as conn:
            yield conn
    monkeypatch.setattr(store, '_connect', connect)
    with connect() as conn:
        conn.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY,status TEXT)')
        conn.execute(store._CREATE_TABLES)
        conn.commit()
    try:
        yield connect
    finally:
        with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA {schema} CASCADE')


@pytest.mark.asyncio
@pytest.mark.parametrize('active',[False,True])
async def test_terminal_cleanup_matches_current_session_and_preserves_recurrence(isolated_store, active):
    sid = str(uuid4()); newer = str(uuid4()); schedule = str(uuid4())
    next_run = datetime.now(timezone.utc) + timedelta(days=1)
    with isolated_store() as conn:
        conn.execute("INSERT INTO sessions VALUES(%s,'awaiting_review'),(%s,'applying')",(sid,newer))
        conn.execute('INSERT INTO autopilot_schedules(id,user_id,is_active,is_running,last_session_id,next_run_at) VALUES(%s,%s,%s,TRUE,%s,%s)',
                     (schedule,str(uuid4()),active,sid,next_run))
        conn.commit()
    await store.complete_terminal_session(sid)
    with isolated_store() as conn:
        assert conn.execute('SELECT is_running FROM autopilot_schedules WHERE id=%s',(schedule,)).fetchone()[0]
        conn.execute("UPDATE sessions SET status='completed' WHERE id=%s",(sid,));conn.commit()
    await store.complete_terminal_session(sid)
    await store.complete_terminal_session(sid)  # idempotent without a live finalizer
    with isolated_store() as conn:
        row = conn.execute('SELECT is_running,is_active,last_session_id,next_run_at FROM autopilot_schedules WHERE id=%s',(schedule,)).fetchone()
        assert row == (False,active,sid,next_run)
        # A newer run owns the schedule now. An old stop must not free it.
        conn.execute('UPDATE autopilot_schedules SET is_running=TRUE,last_session_id=%s WHERE id=%s',(newer,schedule));conn.commit()
    await store.complete_terminal_session(sid)
    with isolated_store() as conn:
        assert conn.execute('SELECT is_running FROM autopilot_schedules WHERE id=%s',(schedule,)).fetchone()[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('action', ['approve','skip'])
async def test_email_get_is_read_only_and_drops_bearer_token(monkeypatch, action):
    import httpx
    from fastapi import FastAPI
    app = FastAPI(); app.include_router(autopilot.router)
    monkeypatch.setattr(autopilot,'verify_approval_token',lambda *args:True)
    cancel=AsyncMock();spawn=AsyncMock();cleanup=AsyncMock()
    monkeypatch.setattr(sessions,'cancel_pipeline',cancel)
    monkeypatch.setattr(sessions,'_spawn_background',spawn)
    monkeypatch.setattr(store,'complete_terminal_session',cleanup)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        response = await client.get(f'/api/autopilot/approve/schedule/session?token=secret&action={action}')
    assert response.status_code == 303
    assert response.headers['location'] == 'https://jobhunteragent.com/session/session'
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert 'secret' not in str(response.headers)
    cancel.assert_not_awaited();spawn.assert_not_called();cleanup.assert_not_awaited()


@pytest.mark.asyncio
async def test_email_get_invalid_token_cannot_redirect(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(autopilot,'verify_approval_token',lambda *args:False)
    with pytest.raises(HTTPException) as error:
        await autopilot.review_autopilot_session('s','r',token='invalid')
    assert error.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize('safe', [True,False])
async def test_pipeline_exposes_only_fixed_hydration_failure(monkeypatch, safe):
    from backend.browser.indeed_policy import IndeedPageUnavailable
    from backend.shared.models.schemas import StartSessionRequest
    monkeypatch.setattr(sessions,'_session_is_terminal',lambda _:False)
    monkeypatch.setattr(sessions,'register_emitter',lambda *args:None)
    monkeypatch.setattr(sessions,'unregister_emitter',lambda *args:None)
    monkeypatch.setattr(sessions,'_set_session_status',lambda *args:None)
    monkeypatch.setattr(sessions,'_release_task_slot',AsyncMock())
    monkeypatch.setattr(sessions,'_send_completion_notifications',AsyncMock())
    error = IndeedPageUnavailable() if safe else RuntimeError('private provider details')
    monkeypatch.setattr(sessions,'_stream_graph',AsyncMock(side_effect=error))
    emit=AsyncMock();monkeypatch.setattr(sessions,'_emit',emit)
    await sessions._run_pipeline('offline',StartSessionRequest(keywords=['Engineer']),object())
    errors=[call.args[2] for call in emit.await_args_list if call.args[1] in ('error','done')]
    message = str(error) if safe else 'An internal error occurred'
    assert errors[0]['message'] == message
    assert errors[1]['error'] == message
    assert 'private provider' not in str(errors)


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['start', 'resume', 'recovered'])
async def test_provider_failure_clears_terminal_schedule_and_queue(monkeypatch, entry):
    from backend.shared.models.schemas import StartSessionRequest
    from backend.shared import task_queue
    sid = 'offline-terminal-error'
    monkeypatch.setattr(sessions, 'session_registry', {sid: {'status': 'applying'}})
    monkeypatch.setattr(sessions, '_session_is_terminal', lambda _: False)
    monkeypatch.setattr(session_store, 'get_session_by_id', lambda _: {'status': 'paused'})
    monkeypatch.setattr(sessions, 'register_emitter', lambda *args: None)
    monkeypatch.setattr(sessions, 'unregister_emitter', lambda *args: None)
    monkeypatch.setattr(sessions, '_emit', AsyncMock())
    monkeypatch.setattr(sessions, '_send_completion_notifications', AsyncMock())
    monkeypatch.setattr(sessions, '_stream_graph', AsyncMock(side_effect=RuntimeError('provider failed')))
    order = []
    def terminal(session_id, status):
        sessions.session_registry[session_id]['status'] = status
        order.append('terminal')
    async def cleanup(session_id):
        assert sessions.session_registry[session_id]['status'] == 'failed'
        order.append('schedule')
    monkeypatch.setattr(sessions, '_set_session_status', terminal)
    monkeypatch.setattr(store, 'complete_terminal_session', cleanup)
    monkeypatch.setattr(task_queue, 'mark_complete', AsyncMock(side_effect=lambda _: order.append('slot')))
    if entry == 'start':
        await sessions._run_pipeline(sid, StartSessionRequest(keywords=['Engineer']), object())
    elif entry == 'resume':
        await sessions._resume_pipeline(sid, object(), resume_value={})
    else:
        await sessions._resume_stalled_pipeline(sid, object(), {})
    assert order == ['terminal', 'schedule', 'slot']
