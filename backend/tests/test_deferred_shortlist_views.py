"""Live, reconnect and GET shortlist views expose only deferred review candidates."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from backend.gateway.routes import sessions
from backend.shared.models.schemas import ScoredJob, JobListing, JobBoard


@pytest.mark.asyncio
@pytest.mark.parametrize('surface', ['live', 'reconnect', 'get'])
@pytest.mark.parametrize('status', ['awaiting_review', 'applying'])
async def test_deferred_review_subset_survives_transport(monkeypatch, surface, status):
    from backend.gateway import deps
    jobs=[ScoredJob(job=JobListing(id=jid,title='Engineer',company='Example',location='Remote',
                                  url='https://www.indeed.com/viewjob?jk='+jid,board=JobBoard.INDEED),
                    score=score,eligibility_status=verdict)
          for jid,score,verdict in [('already-applied',99,'met'),('needs-review',80,'unknown')]]
    cv={'status':status,'scored_jobs':jobs,'pending_eligibility_review_ids':['needs-review']}
    graph=SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values=cv,
        next=('shortlist_review',) if status=='awaiting_review' else ())))
    checkpointer=SimpleNamespace(aget=AsyncMock(return_value={'channel_values':cv}))
    monkeypatch.setattr(sessions, 'session_registry', {'s':{'status':status,'user_id':'owner'}})
    monkeypatch.setattr(sessions, '_set_session_status', lambda sid,value:sessions.session_registry[sid].update(status=value))
    monkeypatch.setattr(sessions, '_overlay_db_app_counts', lambda sid,result:result)
    monkeypatch.setattr('backend.shared.session_store.get_session_by_id', lambda _:None)
    monkeypatch.setattr(deps, 'get_current_user', lambda _:{'id':'owner'})
    monkeypatch.setattr(deps, 'verify_session_owner', AsyncMock())
    if surface=='live':
        emit=AsyncMock();monkeypatch.setattr(sessions, '_emit', emit)
        await sessions._handle_shortlist_interrupt('s',graph,{})
        result=emit.await_args_list[0].args[2]
    elif surface=='reconnect':
        frames=[frame async for frame in sessions._synthesise_snapshot('s',checkpointer,graph)]
        frame=next(frame for frame in frames if frame.startswith('event: shortlist_review'))
        result=json.loads(frame.split('data: ',1)[1])
    else:
        result=await sessions.get_session('s',SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            graph=graph,checkpointer=checkpointer))))
    expected=['needs-review'] if surface=='live' or status=='awaiting_review' else ['already-applied','needs-review']
    assert [sj['job']['id'] for sj in result['scored_jobs']] == expected
