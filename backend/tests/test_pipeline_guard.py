import asyncio
import pytest
from backend.shared.pipeline_guard import single_pipeline_run, is_pipeline_active, cancel_pipeline

@pytest.mark.asyncio
async def test_resume_during_active_run_does_not_start_a_second_worker():
    entered=asyncio.Event(); release=asyncio.Event(); calls=[]
    @single_pipeline_run
    async def run(session_id):
        calls.append(session_id); entered.set(); await release.wait()
    first=asyncio.create_task(run('one'))
    await entered.wait()
    await run('one')
    assert calls == ['one']
    assert is_pipeline_active('one')
    release.set(); await first
    await run('one')
    assert calls == ['one','one']
    assert not is_pipeline_active('one')

@pytest.mark.asyncio
async def test_cancel_stops_worker_and_releases_session():
    entered=asyncio.Event(); cleanup=[]
    @single_pipeline_run
    async def run(session_id):
        try:
            entered.set(); await asyncio.Event().wait()
        finally:
            cleanup.append('closed')
    task=asyncio.create_task(run('cancel'))
    await entered.wait()
    await cancel_pipeline('cancel')
    assert task.cancelled()
    assert cleanup == ['closed']
    assert not is_pipeline_active('cancel')
