from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.gateway.routes import sessions
from backend.orchestrator.pipeline import graph as pipeline


@pytest.mark.asyncio
async def test_coach_interrupt_never_advertises_discovery(monkeypatch):
    events = AsyncMock()
    monkeypatch.setattr(sessions, '_emit', events)
    monkeypatch.setattr(sessions, '_set_session_status', lambda *args: None)
    monkeypatch.setattr(sessions, '_set_session_counts', lambda *args: None)
    async def chunks(*args, **kwargs):
        yield {'data': {'status': 'discovering', 'coach_output': {}},
               'interrupts': (SimpleNamespace(value={'stage': 'coach_review'}),)}
    stage = await sessions._stream_graph_bound('s', SimpleNamespace(astream=chunks), {}, {})
    assert stage == 'coach_review'
    assert not any(call.args[1] == 'discovery' or call.args[2].get('status') == 'discovering'
                   for call in events.await_args_list)


@pytest.mark.asyncio
async def test_discovery_result_emitted_only_after_discovery_finishes(monkeypatch):
    events = AsyncMock()
    monkeypatch.setattr(sessions, '_emit', events)
    monkeypatch.setattr(sessions, '_set_session_status', lambda *args: None)
    monkeypatch.setattr(sessions, '_set_session_counts', lambda *args: None)
    async def chunks(*args, **kwargs):
        yield {'data': {'status': 'discovering'}, 'interrupts': ()}
        yield {'data': {'status': 'scoring', 'discovered_jobs': [object()],
                       'agent_statuses': {'discovery': 'done (1 listings)'}}, 'interrupts': ()}
    await sessions._stream_graph_bound('s', SimpleNamespace(astream=chunks), {}, {})
    results = [call.args[2] for call in events.await_args_list if call.args[1] == 'discovery']
    assert results == [{'status': 'scoring', 'jobs_found': 1}]


@pytest.mark.asyncio
async def test_approved_coach_gate_advances_to_discovery(monkeypatch):
    monkeypatch.setattr(pipeline, 'interrupt', lambda _: {'approved': True})
    result = await pipeline.coach_review_gate({'session_id': 's', 'coach_output': SimpleNamespace(model_dump=lambda: {}), 'status': 'coaching'})
    assert result['status'] == 'discovering'
