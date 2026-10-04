"""Real Redis admission races use only unique, local test keys; no shared flush."""
import asyncio
import uuid
from types import SimpleNamespace
from urllib.parse import urlsplit
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from redis.asyncio import Redis

from backend.shared import task_queue
from backend.shared.config import settings


@pytest_asyncio.fixture
async def queue(monkeypatch):
    if urlsplit(settings.REDIS_URL).hostname not in ('localhost', '127.0.0.1', '::1'):
        pytest.fail('Queue tests require local Redis; refusing remote connection')
    client = Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
    await client.ping()
    prefix = 'taskq-test:' + uuid.uuid4().hex
    monkeypatch.setattr(task_queue, 'redis_client', SimpleNamespace(client=client))
    monkeypatch.setattr(task_queue, '_PENDING_KEY', prefix + ':pending')
    monkeypatch.setattr(task_queue, '_meta_key', lambda sid: prefix + ':meta:' + sid)
    monkeypatch.setattr(task_queue, '_active_set_key', lambda uid: prefix + ':active:' + uid)
    monkeypatch.setattr(task_queue, '_active_count_key', lambda uid: prefix + ':count:' + uid)
    monkeypatch.setattr(task_queue, '_reservations_key', lambda uid: prefix + ':reserved:' + uid)
    try:
        yield client
    finally:
        keys = [key async for key in client.scan_iter(prefix + ':*')]
        if keys:
            await client.delete(*keys)
        await client.aclose()


@pytest.mark.asyncio
async def test_parallel_pending_admission_reserves_at_most_user_limit(queue):
    accepted = await asyncio.gather(*(task_queue.enqueue_session(str(i), 'owner') for i in range(25)))
    assert sum(accepted) == task_queue.MAX_CONCURRENT_PER_USER
    assert await queue.llen(task_queue._PENDING_KEY) == task_queue.MAX_CONCURRENT_PER_USER
    assert await task_queue.get_user_active_count('owner') == task_queue.MAX_CONCURRENT_PER_USER
    assert await task_queue.enqueue_session('other-user-job', 'other-owner') is True


@pytest.mark.asyncio
async def test_duplicate_lifecycle_calls_do_not_inflate_or_release_another_slot(queue):
    assert await task_queue.enqueue_session('a', 'owner')
    assert await task_queue.enqueue_session('a', 'owner')
    assert await queue.llen(task_queue._PENDING_KEY) == 1
    await asyncio.gather(task_queue.mark_active('a'), task_queue.mark_active('a'))
    assert await task_queue.get_user_active_count('owner') == 1
    assert await queue.llen(task_queue._PENDING_KEY) == 0
    assert await task_queue.enqueue_session('b', 'owner')
    await task_queue.mark_active('b')
    await asyncio.gather(task_queue.mark_complete('a'), task_queue.mark_complete('a'))
    assert await task_queue.get_user_active_count('owner') == 1
    # Redis admission is not a finality policy: authorized retry may reuse ID.
    assert await task_queue.enqueue_session('a', 'owner') is True
    assert await task_queue.get_user_active_count('owner') == 2


@pytest.mark.asyncio
async def test_admission_never_reassigns_existing_session_owner(queue):
    assert await task_queue.enqueue_session('same-id', 'alice')
    assert await task_queue.enqueue_session('same-id', 'bob') is False
    assert await queue.hget(task_queue._meta_key('same-id'), 'user_id') == 'alice'
    assert await task_queue.get_user_active_count('bob') == 0


@pytest.fixture
def launches(monkeypatch):
    from backend.gateway.routes import sessions
    from backend.gateway import deps
    from backend.shared import session_store, resume_store
    monkeypatch.setattr(settings, 'INDEED_ONLY', False)
    monkeypatch.setattr(deps, 'get_model_user', lambda _: {'id':'owner'})
    monkeypatch.setattr(sessions, 'session_registry', {})
    monkeypatch.setattr(sessions, 'event_logs', {})
    monkeypatch.setattr(sessions, 'sse_subscribers', {})
    monkeypatch.setattr(sessions, 'upsert_session', MagicMock())
    monkeypatch.setattr(session_store, 'get_session_by_id', lambda _: {
        'user_id':'owner', 'keywords':['Engineer'], 'locations':[], 'remote_only':True,
        'salary_min':None, 'resume_text_snippet':'Factual resume', 'status':'completed'})
    monkeypatch.setattr(resume_store, 'get_resume', lambda _: None)
    spawned=[]
    def spawn(coro):
        coro.close()  # Even the red regression cannot execute a provider.
        spawned.append(True)
    monkeypatch.setattr(sessions, '_spawn_background', spawn)
    return sessions, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(graph=object()))), spawned


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['start', 'rerun'])
@pytest.mark.parametrize('failed_step', ['enqueue_session', 'mark_active'])
async def test_queue_failure_cannot_launch_pipeline(monkeypatch, launches, entry, failed_step):
    from backend.shared.models.schemas import StartSessionRequest
    sessions, request, spawned = launches
    monkeypatch.setattr(task_queue, 'enqueue_session', AsyncMock(return_value=True))
    monkeypatch.setattr(task_queue, 'mark_active', AsyncMock())
    monkeypatch.setattr(task_queue, failed_step, AsyncMock(side_effect=RuntimeError('private connection detail')))
    with pytest.raises(HTTPException) as error:
        if entry == 'start':
            await sessions.start_session(StartSessionRequest(keywords=['Engineer']), request)
        else:
            await sessions.rerun_session('old', sessions.RerunRequest(), request)
    assert error.value.status_code == 503
    assert 'private' not in str(error.value.detail)
    assert spawned == []
    sessions.upsert_session.assert_not_called()


@pytest.mark.asyncio
async def test_resume_reuses_claim_and_expired_claim_cannot_bypass_full_limit(monkeypatch, queue):
    from backend.gateway.routes import sessions
    from backend.shared import model_execution
    monkeypatch.setattr(sessions, 'session_registry', {'resume-id':{'user_id':'owner','status':'awaiting_review'}})
    async def own_scope(owner, operation):
        assert owner == 'owner'
        return await operation()
    monkeypatch.setattr(model_execution, 'run_model_task', own_scope)
    stream = AsyncMock(return_value='shortlist_review')
    monkeypatch.setattr(sessions, '_stream_graph_bound', stream)
    await task_queue.admit_session('resume-id', 'owner')
    deadline = await queue.zscore(task_queue._reservations_key('owner'), 'resume-id')
    await sessions._stream_graph('resume-id', object(), {}, None)
    assert await task_queue.get_user_active_count('owner') == 1
    assert await queue.zscore(task_queue._reservations_key('owner'), 'resume-id') == deadline
    # Simulate this fixed lease and its metadata expiring, without waiting a day.
    await queue.zadd(task_queue._reservations_key('owner'), {'resume-id':0})
    await queue.delete(task_queue._meta_key('resume-id'))
    for i in range(task_queue.MAX_CONCURRENT_PER_USER):
        assert await task_queue.enqueue_session('replacement-' + str(i), 'owner')
    stream.reset_mock()
    monkeypatch.setattr(sessions, '_set_session_status', lambda sid, status: sessions.session_registry[sid].update(status=status))
    emit = AsyncMock(); monkeypatch.setattr(sessions, '_emit', emit)
    assert await sessions._stream_graph('resume-id', object(), {}, None) == 'queue_admission'
    assert sessions.session_registry['resume-id']['status'] == 'paused'
    assert emit.await_args_list[0].args[2]['error_category'] == 'queue_admission'
    assert emit.await_args_list[1].args[2]['status'] == 'paused'
    stream.assert_not_awaited()


@pytest.mark.asyncio
async def test_restart_legacy_active_claim_is_preserved_with_its_existing_expiry(queue):
    await queue.hset(task_queue._meta_key('legacy'), mapping={'user_id':'owner','status':'active'})
    await queue.expire(task_queue._meta_key('legacy'), 40)
    await queue.sadd(task_queue._active_set_key('owner'), 'legacy')
    assert await task_queue.get_user_active_count('owner') == 1
    deadline = await queue.zscore(task_queue._reservations_key('owner'), 'legacy')
    await task_queue.admit_session('legacy', 'owner')
    assert await queue.zscore(task_queue._reservations_key('owner'), 'legacy') == deadline
    assert await queue.ttl(task_queue._meta_key('legacy')) <= 40


@pytest.mark.asyncio
async def test_graph_completion_releases_claim(monkeypatch, queue):
    from backend.gateway.routes import sessions
    from backend.shared import model_execution
    monkeypatch.setattr(sessions, 'session_registry', {'s':{'user_id':'owner','status':'applying'}})
    async def own_scope(owner, operation): return await operation()
    monkeypatch.setattr(model_execution, 'run_model_task', own_scope)
    async def complete(*args):
        sessions.session_registry['s']['status'] = 'completed'
    monkeypatch.setattr(sessions, '_stream_graph_bound', complete)
    await sessions._stream_graph('s', object(), {}, None)
    assert await task_queue.get_user_active_count('owner') == 0


@pytest.mark.asyncio
async def test_autopilot_admission_failure_has_no_background_work(monkeypatch):
    from backend.shared import autopilot_runner as runner, model_access, resume_store
    from backend.gateway.routes import sessions
    monkeypatch.setattr(model_access, 'require_model_access', lambda _:None)
    monkeypatch.setattr(resume_store, 'get_latest_resume_for_user', lambda _:(b'Synthetic Applicant\nSoftware engineer.', '.txt'))
    monkeypatch.setattr(task_queue, 'enqueue_session', AsyncMock(side_effect=RuntimeError('private connection detail')))
    spawned=MagicMock();monkeypatch.setattr(sessions, '_spawn_background', spawned)
    with pytest.raises(task_queue.QueueUnavailable, match='temporarily unavailable'):
        await runner._run_schedule({'id':'schedule','user_id':'owner','cron_expression':'0 9 * * *'})
    spawned.assert_not_called()


@pytest.mark.asyncio
async def test_autopilot_run_now_returns_recoverable_service_error(monkeypatch):
    from backend.gateway import deps
    from backend.gateway.routes import autopilot
    from backend.shared import autopilot_runner
    monkeypatch.setattr(deps, 'get_current_user', lambda _:{'id':'owner'})
    monkeypatch.setattr(autopilot, 'get_schedule', AsyncMock(return_value={'id':'s','user_id':'owner'}))
    monkeypatch.setattr(autopilot_runner, '_run_schedule', AsyncMock(side_effect=task_queue.QueueUnavailable('Session admission is temporarily unavailable.')))
    with pytest.raises(HTTPException) as error:
        await autopilot.run_now('s', SimpleNamespace())
    assert error.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [RuntimeError('graph failed'), asyncio.CancelledError()])
async def test_graph_error_or_cancel_releases_only_its_claim(monkeypatch, queue, failure):
    from backend.gateway.routes import sessions
    from backend.shared import model_execution
    monkeypatch.setattr(sessions, 'session_registry', {'s':{'user_id':'owner','status':'applying'}})
    async def own_scope(owner, operation): return await operation()
    monkeypatch.setattr(model_execution, 'run_model_task', own_scope)
    monkeypatch.setattr(sessions, '_stream_graph_bound', AsyncMock(side_effect=failure))
    await task_queue.admit_session('other-run', 'owner')
    with pytest.raises(type(failure)):
        await sessions._stream_graph('s', object(), {}, None)
    assert await task_queue.get_user_active_count('owner') == 1
    assert await queue.zscore(task_queue._reservations_key('owner'), 'other-run') is not None


@pytest.mark.asyncio
async def test_redis_failure_on_recovery_pauses_visibly_before_providers(monkeypatch):
    from backend.gateway.routes import sessions
    from backend.shared import model_execution
    monkeypatch.setattr(sessions, 'session_registry', {'s':{'user_id':'owner','status':'recovering'}})
    async def own_scope(owner, operation): return await operation()
    monkeypatch.setattr(model_execution, 'run_model_task', own_scope)
    monkeypatch.setattr(task_queue, 'enqueue_session', AsyncMock(side_effect=RuntimeError('private Redis URL')))
    monkeypatch.setattr(sessions, '_set_session_status', lambda sid, status: sessions.session_registry[sid].update(status=status))
    emit=AsyncMock(); monkeypatch.setattr(sessions, '_emit', emit)
    stream=AsyncMock();monkeypatch.setattr(sessions, '_stream_graph_bound', stream)
    assert await sessions._stream_graph('s', object(), {}, None) == 'queue_admission'
    assert sessions.session_registry['s']['status'] == 'paused'
    stream.assert_not_awaited()
    assert 'private' not in str(emit.await_args_list)
    assert 'temporarily unavailable' in emit.await_args_list[0].args[2]['message']


@pytest.mark.asyncio
async def test_authorized_checkpoint_resume_can_reacquire_completed_redis_slot(monkeypatch, queue):
    from backend.gateway.routes import sessions
    from backend.gateway import deps
    from backend.shared import model_execution, model_access, session_store
    await task_queue.admit_session('retry-id', 'owner')
    await task_queue.mark_complete('retry-id')
    # Durable lifecycle permits this reviewed checkpoint; Redis's old completion
    # must not override the application's retry/resume authorization.
    monkeypatch.setattr(session_store, 'get_session_by_id', lambda _:{'user_id':'owner','status':'paused'})
    monkeypatch.setattr(deps, 'get_current_user', lambda _:{'id':'owner'})
    monkeypatch.setattr(deps, 'verify_session_owner', AsyncMock())
    monkeypatch.setattr(model_access, 'require_model_access', lambda _:None)
    async def own_scope(owner, operation):
        assert owner == 'owner'
        return await operation()
    monkeypatch.setattr(model_execution, 'run_model_task', own_scope)
    monkeypatch.setattr(sessions, 'session_registry', {'retry-id':{'user_id':'owner','status':'paused'}})
    monkeypatch.setattr(sessions, '_set_session_status', lambda sid, status:sessions.session_registry[sid].update(status=status))
    monkeypatch.setattr(sessions, 'event_logs', {})
    monkeypatch.setattr(sessions, 'sse_subscribers', {})
    monkeypatch.setattr(sessions, '_emit', AsyncMock())
    monkeypatch.setattr(sessions, 'register_emitter', MagicMock())
    async def finish(*args):
        sessions.session_registry['retry-id']['status']='completed'
    streamed=AsyncMock(side_effect=finish);monkeypatch.setattr(sessions, '_stream_graph_bound', streamed)
    graph=SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(next=('coach_review',),values={})))
    spawned=[];monkeypatch.setattr(sessions, '_spawn_background', lambda coro:spawned.append(coro))
    await sessions.rewind_session('retry-id', sessions.RewindRequest(checkpoint_id='approved-checkpoint'),
                                 SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(graph=graph))))
    for coro in spawned:await coro
    streamed.assert_awaited_once()
    assert await task_queue.get_user_active_count('owner') == 0


@pytest.mark.asyncio
async def test_autopilot_at_capacity_defers_without_marking_running(monkeypatch):
    from backend.shared import autopilot_runner as runner, model_access, resume_store
    from backend.gateway.routes import sessions
    monkeypatch.setattr(model_access, 'require_model_access', lambda _:None)
    monkeypatch.setattr(resume_store, 'get_latest_resume_for_user', lambda _:(b'Synthetic Applicant\nSoftware engineer.', '.txt'))
    monkeypatch.setattr(task_queue, 'enqueue_session', AsyncMock(return_value=False))
    defer=AsyncMock(); monkeypatch.setattr(runner, 'defer_run', defer, raising=False)
    mark=AsyncMock(); monkeypatch.setattr(runner, 'mark_run', mark)
    spawned=MagicMock(); monkeypatch.setattr(sessions, '_spawn_background', spawned)
    with pytest.raises(task_queue.QueueAtCapacity):
        await runner._run_schedule({'id':'schedule','user_id':'owner','cron_expression':'0 9 * * *'})
    defer.assert_awaited_once()
    mark.assert_not_awaited()
    spawned.assert_not_called()


@pytest.mark.asyncio
async def test_autopilot_run_now_capacity_is_429_not_triggered(monkeypatch):
    from backend.gateway import deps
    from backend.gateway.routes import autopilot
    from backend.shared import autopilot_runner
    monkeypatch.setattr(deps, 'get_current_user', lambda _:{'id':'owner'})
    monkeypatch.setattr(autopilot, 'get_schedule', AsyncMock(return_value={'id':'s','user_id':'owner'}))
    monkeypatch.setattr(autopilot_runner, '_run_schedule', AsyncMock(side_effect=task_queue.QueueAtCapacity('No session slot')))
    with pytest.raises(HTTPException) as error:
        await autopilot.run_now('s', SimpleNamespace())
    assert error.value.status_code == 429


@pytest.mark.asyncio
async def test_failed_activation_does_not_extend_pending_reservation_forever(monkeypatch, queue):
    assert await task_queue.enqueue_session('pending', 'owner')
    deadline=await queue.zscore(task_queue._reservations_key('owner'), 'pending')
    monkeypatch.setattr(task_queue, 'mark_active', AsyncMock(side_effect=RuntimeError('connection lost')))
    for _ in range(3):
        with pytest.raises(task_queue.QueueUnavailable):
            await task_queue.admit_session('pending', 'owner')
    assert await queue.zscore(task_queue._reservations_key('owner'), 'pending') == deadline
    assert 0 < await queue.ttl(task_queue._meta_key('pending')) <= task_queue.TASK_META_TTL
    await task_queue.mark_complete('pending')
    assert await task_queue.get_user_active_count('owner') == 0
