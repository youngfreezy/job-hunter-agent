"""Stopped sessions remain terminal across stale registries and checkpoint reconnects."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest
from fastapi import HTTPException

from backend.gateway.routes import sessions
from backend.shared import session_store
from backend.shared.db import get_connection


@pytest.mark.asyncio
async def test_kill_updates_registry_as_well_as_durable_status(monkeypatch):
    row = {'user_id': 'user', 'status': 'applying'}
    monkeypatch.setattr('backend.gateway.deps.get_current_user', lambda _: {'id': 'user'})
    monkeypatch.setattr(session_store, 'get_session_by_id', lambda _: row)
    write = MagicMock()
    monkeypatch.setattr(session_store, 'update_session_status', write)
    monkeypatch.setattr(sessions, 'cancel_pipeline', AsyncMock())
    monkeypatch.setattr(sessions, '_release_task_slot', AsyncMock())
    monkeypatch.setattr(sessions, 'unregister_emitter', MagicMock())
    monkeypatch.setitem(sessions.session_registry, 'stopped', {'status': 'applying'})
    assert await sessions.kill_session('stopped', object()) == {'status': 'killed'}
    assert sessions.session_registry['stopped']['status'] == 'completed'
    write.assert_called_once_with('stopped', 'completed', raise_on_error=True)


@pytest.mark.asyncio
async def test_checkpoint_reconnect_never_resurrects_durable_completion(monkeypatch):
    monkeypatch.setattr(session_store, 'get_session_by_id', lambda _: {'status': 'completed'})
    write = MagicMock()
    monkeypatch.setattr(sessions, 'update_session_status', write)
    monkeypatch.setitem(sessions.session_registry, 'stopped', {'status': 'applying'})
    checkpointer = SimpleNamespace(aget=AsyncMock(return_value={'channel_values': {'status': 'applying'}}))
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(next=('shortlist_review',))))
    events = [event async for event in sessions._synthesise_snapshot('stopped', checkpointer, graph)]
    assert any('event: done' in event for event in events)
    assert all('awaiting_review' not in event and '"status": "applying"' not in event for event in events)
    assert sessions.session_registry['stopped']['status'] == 'completed'
    assert all(call.args[1] == 'completed' for call in write.call_args_list)


@pytest.mark.asyncio
async def test_startup_recovery_task_rechecks_terminal_status_before_running(monkeypatch):
    monkeypatch.setattr(session_store, 'get_session_by_id', lambda _: {'status': 'completed'})
    stream = AsyncMock()
    monkeypatch.setattr(sessions, '_stream_graph', stream)
    await sessions._resume_stalled_pipeline('stopped-before-start', MagicMock(), {})
    stream.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_endpoint_rejects_terminal_session_before_checkpoint(monkeypatch):
    monkeypatch.setattr('backend.gateway.deps.get_current_user', lambda _: {'id': 'user'})
    monkeypatch.setattr('backend.gateway.deps.verify_session_owner', AsyncMock())
    monkeypatch.setattr(session_store, 'get_session_by_id', lambda _: {'status': 'completed'})
    graph = SimpleNamespace(aget_state=AsyncMock())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(graph=graph)))
    with pytest.raises(HTTPException) as stopped:
        await sessions.resume_session('stopped', request)
    assert stopped.value.status_code == 409
    graph.aget_state.assert_not_awaited()


@pytest.mark.requires_postgres
def test_shutdown_ignores_stale_terminal_registry_ids_and_startup_cannot_recover_them():
    from alembic import command
    from alembic.config import Config
    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / 'alembic.ini'))
    cfg.set_main_option('script_location', str(backend_dir / 'alembic'))
    command.upgrade(cfg, 'head')
    user_id = str(uuid.uuid4())
    ids = {status: f'test-kill-{uuid.uuid4().hex}' for status in ['completed', 'failed', 'applying', 'awaiting_review']}
    with get_connection() as conn:
        conn.execute('INSERT INTO users (id,email) VALUES (%s,%s)', (user_id, f'{user_id}@test.invalid'))
        for status, sid in ids.items():
            conn.execute('INSERT INTO sessions (id,user_id,status) VALUES (%s,%s,%s)', (sid,user_id,status))
        conn.commit()
    try:
        session_store.mark_sessions_interrupted(list(ids.values()))
        recovered = {item['session_id'] for item in session_store.get_interrupted_sessions()}
        assert ids['completed'] not in recovered
        assert ids['failed'] not in recovered
        assert ids['awaiting_review'] not in recovered
        assert ids['applying'] in recovered
        assert session_store.get_session_by_id(ids['completed'])['status'] == 'completed'
        assert session_store.get_session_by_id(ids['failed'])['status'] == 'failed'
    finally:
        with get_connection() as conn:
            conn.execute('DELETE FROM sessions WHERE user_id=%s', (user_id,))
            conn.execute('DELETE FROM users WHERE id=%s', (user_id,))
            conn.commit()
