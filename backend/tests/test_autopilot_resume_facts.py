"""Schedule launch must ground model facts in the saved canonical file."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from backend.shared import autopilot_runner as runner

@pytest.fixture
def launch(monkeypatch):
    monkeypatch.setattr('backend.shared.autopilot_store.schedule_owner_exists', lambda *_: True)
    from backend.gateway.routes import sessions
    from backend.gateway import main
    from backend.shared import model_access, task_queue, resume_store, session_store
    monkeypatch.setattr(model_access,'require_model_access',lambda uid:None)
    enqueue=AsyncMock(return_value=True);monkeypatch.setattr(task_queue,'enqueue_session',enqueue)
    monkeypatch.setattr(task_queue,'mark_active',AsyncMock())
    monkeypatch.setattr(resume_store,'get_latest_resume_for_user',lambda uid:(b'Synthetic Applicant\nPython AI engineering.', '.txt'))
    monkeypatch.setattr(resume_store,'save_resume',MagicMock())
    monkeypatch.setattr(session_store,'upsert_session',MagicMock())
    monkeypatch.setattr(main,'_app_ref',SimpleNamespace(state=SimpleNamespace(graph=object())))
    calls=[]
    async def run(*args,**kwargs):calls.append((args,kwargs))
    monkeypatch.setattr(sessions,'_run_pipeline',run)
    tasks=[];monkeypatch.setattr(sessions,'_spawn_background',lambda coro:tasks.append(coro))
    monkeypatch.setattr(runner,'mark_run',AsyncMock())
    return calls,tasks,enqueue

@pytest.mark.asyncio
async def test_saved_resume_bytes_become_full_pipeline_facts(launch):
    calls,tasks,_=launch
    await runner._run_schedule({'id':'schedule','user_id':'owner','cron_expression':'0 9 * * *','auto_approve':True})
    for task in tasks:await task
    assert calls[0][0][1].resume_text=='Synthetic Applicant\nPython AI engineering.'

@pytest.mark.asyncio
async def test_unreadable_saved_resume_stops_before_queue_or_pipeline(monkeypatch,launch):
    calls,tasks,enqueue=launch
    monkeypatch.setattr('backend.shared.resume_store.get_latest_resume_for_user',lambda uid:(b'', '.txt'))
    with pytest.raises(ValueError,match='readable saved resume'):
        await runner._run_schedule({'id':'schedule','user_id':'owner','cron_expression':'0 9 * * *','auto_approve':True})
    assert not tasks and not calls
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_deleted_prefetched_schedule_releases_admission_without_starting(monkeypatch, launch):
    calls, tasks, enqueue = launch
    release = AsyncMock()
    monkeypatch.setattr('backend.shared.autopilot_store.schedule_owner_exists', lambda *_: False)
    monkeypatch.setattr('backend.shared.task_queue.mark_complete', release)
    with pytest.raises(ValueError, match='no longer exists'):
        await runner._run_schedule({'id':'schedule','user_id':'owner','cron_expression':'0 9 * * *','auto_approve':True})
    enqueue.assert_awaited_once()
    release.assert_awaited_once_with(enqueue.call_args.args[0])
    assert not calls and not tasks


def test_approval_requires_configured_signing_secret(monkeypatch):
    monkeypatch.setattr(runner,'get_settings',lambda:SimpleNamespace(NEXTAUTH_SECRET=''))
    assert runner.verify_approval_token('schedule','session','9999999999:invalid') is False
    with pytest.raises(ValueError,match='signing secret'):
        runner.generate_approval_token('schedule','session')

@pytest.mark.parametrize('raw,suffix,status', [(b'not PDF','pdf',400),(b'','txt',422),(b'x'*(10*1024*1024+1),'txt',413)])
def test_shared_resume_parser_rejects_invalid_or_empty_facts(raw,suffix,status):
    from backend.shared.resume_text import extract_resume_text,ResumeTextError
    with pytest.raises(ResumeTextError) as error:extract_resume_text(raw,suffix)
    assert error.value.status_code==status

@pytest.mark.asyncio
async def test_run_now_reports_unreadable_resume_in_app(monkeypatch):
    from backend.gateway.routes import autopilot
    from backend.gateway import deps
    from fastapi import HTTPException
    monkeypatch.setattr(deps,'get_current_user',lambda request:{'id':'owner'})
    monkeypatch.setattr(autopilot,'get_schedule',AsyncMock(return_value={'id':'s','user_id':'owner'}))
    monkeypatch.setattr(runner,'_run_schedule',AsyncMock(side_effect=ValueError('Autopilot needs a readable saved resume.')))
    with pytest.raises(HTTPException) as error:await autopilot.run_now('s',SimpleNamespace())
    assert error.value.status_code==422
    assert 'readable saved resume' in error.value.detail
