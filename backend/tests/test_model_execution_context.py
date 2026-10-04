import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request
from starlette.responses import Response

from backend.shared import model_access, model_execution
from backend.shared.config import settings


@pytest.fixture(autouse=True)
def funding(monkeypatch):
    monkeypatch.setattr(settings, 'BROWSERBASE_CONTEXT_USER_ID', 'owner')
    monkeypatch.setattr(settings, 'LLM_PROVIDER', 'anthropic')
    monkeypatch.setattr(settings, 'ANTHROPIC_API_KEY', 'owner-key')
    # Queue lifecycle is exercised with real Redis in test_task_queue_admission.
    monkeypatch.setattr('backend.shared.task_queue.admit_session', AsyncMock())
    monkeypatch.setattr('backend.shared.model_key_store.get_model_key', lambda uid: {'alice': 'alice-key', 'bob': 'bob-key'}.get(uid))
    with model_access.model_user_scope(None):
        yield


@pytest.mark.asyncio
async def test_concurrent_background_operations_use_distinct_keys_and_restore_parent():
    async def capture():
        await asyncio.sleep(0)
        return model_access.current_model_user(), model_access.current_model_credentials().api_key
    with model_access.model_user_scope('owner'):
        result = await asyncio.gather(model_execution.run_model_task('alice', capture),
                                      model_execution.run_model_task('bob', capture))
        assert model_access.current_model_user() == 'owner'
    assert result == [('alice', 'alice-key'), ('bob', 'bob-key')]
    assert model_access.current_model_user() is None


@pytest.mark.asyncio
async def test_missing_key_never_starts_background_operation():
    operation = AsyncMock()
    with model_access.model_user_scope('owner'):
        with pytest.raises(model_access.ModelAccessRequired):
            await model_execution.run_model_task('missing-key', operation)
    operation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['initial', 'registry', 'durable'])
async def test_graph_start_and_recovery_bind_stored_owner_not_inherited_identity(monkeypatch, source):
    from backend.gateway.routes import sessions
    monkeypatch.setattr(sessions, 'session_registry', {'s': {'user_id': 'alice'}} if source == 'registry' else {})
    monkeypatch.setattr('backend.shared.session_store.get_session_by_id', lambda _: {'user_id': 'alice'} if source == 'durable' else None)
    observed = []
    async def chunks(*args, **kwargs):
        observed.append(model_access.current_model_credentials().api_key)
        if False:
            yield None
    with model_access.model_user_scope('owner'):
        await sessions._stream_graph('s', SimpleNamespace(astream=chunks), {},
                                     {'user_id':'alice'} if source == 'initial' else None)
        assert model_access.current_model_user() == 'owner'
    assert observed == ['alice-key']


@pytest.mark.asyncio
async def test_unowned_recovery_cannot_inherit_owner_funding(monkeypatch):
    from backend.gateway.routes import sessions
    monkeypatch.setattr(sessions, 'session_registry', {})
    monkeypatch.setattr('backend.shared.session_store.get_session_by_id', lambda _: None)
    graph = SimpleNamespace(astream=AsyncMock())
    with model_access.model_user_scope('owner'):
        with pytest.raises(model_access.ModelAccessRequired):
            await sessions._stream_graph('s', graph, {}, None)
    graph.astream.assert_not_called()


@pytest.mark.asyncio
async def test_exempt_request_starts_unbound_and_does_not_leak_identity():
    from backend.gateway.middleware.jwt_auth import JWTAuthMiddleware
    middleware = JWTAuthMiddleware(app=None)
    req = Request({'type':'http', 'method':'GET', 'path':'/api/health', 'headers':[], 'query_string':b''})
    async def next_request(request):
        assert model_access.current_model_user() is None
        model_access.bind_model_user('alice')
        return Response('ok')
    with model_access.model_user_scope('owner'):
        await middleware.dispatch(req, next_request)
        assert model_access.current_model_user() == 'owner'


def test_paid_request_preflight_requires_own_key(monkeypatch):
    from backend.gateway import deps
    req = Request({'type':'http', 'headers':[]})
    req.state.user_email = 'visitor@example.com'
    monkeypatch.setattr(deps, 'get_or_create_user', lambda _: {'id':'missing-key'})
    with pytest.raises(model_access.ModelAccessRequired) as error:
        deps.get_model_user(req)
    assert error.value.status_code == 428
    assert model_access.current_model_user() == 'missing-key'


@pytest.mark.asyncio
async def test_interview_answer_cannot_spend_for_another_users_session(monkeypatch):
    from backend.gateway.routes import interview_prep
    monkeypatch.setattr(interview_prep, 'get_model_user', lambda _: {'id':'alice'})
    monkeypatch.setattr(interview_prep, '_prep_registry', {'private':{'user_id':'bob'}})
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        await interview_prep.submit_answer(None, 'private', SimpleNamespace(question_id='q', answer='private'))
    assert error.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize('module,runner,registry', [
    ('career_pivot', '_run_pivot_pipeline', '_pivot_registry'),
    ('freelance', '_run_freelance_pipeline', '_fl_registry'),
    ('interview_prep', '_run_prep_pipeline', '_prep_registry'),
])
async def test_auxiliary_backgrounds_bind_user_and_report_missing_key(monkeypatch, module, runner, registry):
    from importlib import import_module
    route = import_module('backend.gateway.routes.' + module)
    rows = {'good': {'status':'starting'}, 'bad': {'status':'starting'}}
    monkeypatch.setattr(route, registry, rows)
    keys = []
    async def chunks(*args, **kwargs):
        keys.append(model_access.current_model_credentials().api_key)
        if module == 'interview_prep':
            yield {'data': {
                'company_brief': {'mission': 'Fixture mission', 'culture': 'Unknown',
                                  'things_to_mention': ['Relevant experience'], 'interview_tips': ['Be specific']},
                'questions': [{'id': f'q{i}', 'category': 'technical', 'question': f'Practice question {i}',
                               'source': 'ai_generated'} for i in range(15)],
            }}
    graph = SimpleNamespace(astream=chunks)
    with model_access.model_user_scope('owner'):
        await getattr(route, runner)('good', graph, {}, {'user_id':'alice'})
        await getattr(route, runner)('bad', graph, {}, {'user_id':'missing-key'})
        assert model_access.current_model_user() == 'owner'
    assert keys == ['alice-key']
    assert rows['good']['status'] == ('ready' if module == 'interview_prep' else 'completed')
    assert rows['bad']['status'] == 'failed'


@pytest.mark.asyncio
@pytest.mark.parametrize('module,registry,endpoint', [
    ('career_pivot', '_pivot_registry', 'stream_pivot'),
    ('career_pivot', '_pivot_registry', 'get_pivot'),
    ('freelance', '_fl_registry', 'stream_freelance'),
    ('freelance', '_fl_registry', 'get_freelance'),
    ('interview_prep', '_prep_registry', 'stream_prep'),
    ('interview_prep', '_prep_registry', 'get_prep'),
    ('interview_prep', '_prep_registry', 'end_prep'),
])
@pytest.mark.parametrize('email,status', [(None,401), ('alice@example.com',403)])
async def test_auxiliary_reports_and_streams_reject_nonowners(monkeypatch, module, registry, endpoint, email, status):
    from importlib import import_module
    from fastapi import HTTPException
    from backend.gateway import deps
    route = import_module('backend.gateway.routes.' + module)
    rows = {'private': {'user_id':'bob', 'status':'ready'}}
    monkeypatch.setattr(route, registry, rows)
    monkeypatch.setattr(deps, 'get_or_create_user', lambda _: {'id':'alice'})
    req = Request({'type':'http', 'headers':[]})
    req.state.user_email = email
    with pytest.raises(HTTPException) as error:
        await getattr(route, endpoint)(req, 'private')
    assert error.value.status_code == status
    assert rows['private']['status'] == 'ready'
    subscribers = getattr(route, registry.replace('_registry', '_subscribers'))
    assert not subscribers.get('private')
