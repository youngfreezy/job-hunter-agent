from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException
import pytest

from backend.gateway.routes import sessions
from backend.shared import session_store


@pytest.fixture
def stopped_run(monkeypatch):
    row = {'status': 'completed'}
    monkeypatch.setattr(session_store, 'get_session_by_id', lambda _: row)
    monkeypatch.setattr('backend.gateway.deps.get_current_user', lambda _: {'id': 'owner'})
    monkeypatch.setattr('backend.gateway.deps.verify_session_owner', AsyncMock())
    write = MagicMock()
    monkeypatch.setattr(sessions, 'update_session_status', write)
    monkeypatch.setattr(sessions, '_emit', AsyncMock())
    spawn = MagicMock(side_effect=lambda coro: coro.close())
    monkeypatch.setattr(sessions, '_spawn_background', spawn)
    stream = AsyncMock()
    monkeypatch.setattr(sessions, '_stream_graph', stream)
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(
        values={'application_queue': ['job']}, next=('shortlist_review',))), aupdate_state=AsyncMock())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(graph=graph)))
    body = SimpleNamespace(approved_job_ids=['job'], approved=True, use_original=True,
        feedback='', edited_resume=None, checkpoint_id='checkpoint')
    return row, graph, request, body, write, spawn, stream


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ['review_shortlist', 'submit_coach_review', 'rewind_session', 'resume_session', 'steer_session'])
@pytest.mark.parametrize('status', ['completed', 'failed'])
async def test_terminal_session_rejects_all_restart_endpoints_before_mutation(stopped_run, endpoint, status):
    row, graph, request, body, write, spawn, _ = stopped_run
    row['status'] = status
    args = ('terminal', request) if endpoint == 'resume_session' else ('terminal', body, request)
    with pytest.raises(HTTPException) as error:
        await getattr(sessions, endpoint)(*args)
    assert error.value.status_code == 409
    graph.aget_state.assert_not_awaited()
    graph.aupdate_state.assert_not_awaited()
    write.assert_not_called()
    spawn.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ['review_shortlist', 'submit_coach_review', 'rewind_session', 'resume_session', 'steer_session'])
async def test_stop_during_checkpoint_read_does_not_revive_session(stopped_run, endpoint):
    row, graph, request, body, write, spawn, _ = stopped_run
    row['status'] = 'awaiting_review'
    async def read(_):
        row['status'] = 'completed'
        return SimpleNamespace(values={'application_queue': ['job']}, next=('shortlist_review',))
    graph.aget_state.side_effect = read
    args = ('terminal', request) if endpoint == 'resume_session' else ('terminal', body, request)
    with pytest.raises(HTTPException) as error:
        await getattr(sessions, endpoint)(*args)
    assert error.value.status_code == 409
    graph.aupdate_state.assert_not_awaited()
    write.assert_not_called()
    spawn.assert_not_called()


@pytest.mark.asyncio
async def test_queued_resume_and_initial_start_recheck_durable_stop(stopped_run):
    _, graph, _, _, write, _, stream = stopped_run
    await sessions._resume_pipeline('terminal', graph, resume_value={'approved': True})
    await sessions._run_pipeline('terminal', MagicMock(), graph)
    stream.assert_not_awaited()
    write.assert_not_called()


@pytest.mark.asyncio
async def test_nonterminal_review_still_resumes(stopped_run):
    row, _, request, body, write, spawn, _ = stopped_run
    row['status'] = 'awaiting_review'
    await sessions.review_shortlist('active', body, request)
    write.assert_called_once_with('active', 'applying')
    spawn.assert_called_once()
