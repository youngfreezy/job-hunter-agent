from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.gateway.routes import sessions
from backend.gateway import deps
from backend.shared import screenshot_store


@pytest.mark.asyncio
@pytest.mark.parametrize('handler', ['list_screenshots','get_screenshot','list_artifacts'])
@pytest.mark.parametrize('signed_in', [False,True])
async def test_session_artifacts_refuse_unauthenticated_or_foreign_owner_before_read(monkeypatch,handler,signed_in):
    def user(_request):
        if not signed_in: raise HTTPException(401,'Sign in required')
        return {'id':'visitor'}
    monkeypatch.setattr(deps,'get_current_user',user)
    owner=AsyncMock(side_effect=HTTPException(403,'Not your session'))
    monkeypatch.setattr(deps,'verify_session_owner',owner)
    reader=MagicMock(side_effect=AssertionError('Private artifacts must not be read'))
    for name in ('get_screenshots_for_session','get_screenshot','get_artifacts_for_session'):
        monkeypatch.setattr(screenshot_store,name,reader)
    args=('foreign-session',7,SimpleNamespace()) if handler=='get_screenshot' else ('foreign-session',SimpleNamespace())
    with pytest.raises(HTTPException) as error:
        await getattr(sessions,handler)(*args)
    assert error.value.status_code==(403 if signed_in else 401)
    reader.assert_not_called()


@pytest.mark.requires_postgres
def test_screenshot_id_cannot_be_reused_under_another_owned_session():
    first=screenshot_store.store_screenshot_bytes('artifact-owned-a','job','private-a'.encode())
    second=screenshot_store.store_screenshot_bytes('artifact-owned-b','job','private-b'.encode())
    assert screenshot_store.get_screenshot(first,session_id='artifact-owned-a')== (b'private-a','image/png')
    assert screenshot_store.get_screenshot(second,session_id='artifact-owned-a') is None

@pytest.mark.asyncio
async def test_disk_screenshot_must_belong_to_requested_session(monkeypatch,tmp_path):
    import tempfile
    from backend.shared import application_store
    directory=tmp_path/'jobhunter_screenshots';directory.mkdir()
    foreign=directory/'foreign.png';foreign.write_bytes(b'private')
    monkeypatch.setattr(tempfile,'gettempdir',lambda:str(tmp_path))
    monkeypatch.setattr(deps,'get_current_user',lambda request:{'id':'owner'})
    monkeypatch.setattr(deps,'verify_session_owner',AsyncMock())
    monkeypatch.setattr(application_store,'get_results_for_session',lambda sid:[{'screenshot_path':str(directory/'own.png')}])
    with pytest.raises(HTTPException) as error:
        await sessions.get_application_screenshot('owned-session',str(foreign),SimpleNamespace())
    assert error.value.status_code==404

@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_application_log_preserves_uncertain_classification():
    from backend.shared import application_store
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    cfg=Config(str(root/'alembic.ini'));cfg.set_main_option('script_location',str(root/'alembic'))
    command.upgrade(cfg,'head')
    await application_store.ensure_table()
    from uuid import uuid4
    from backend.shared.db import get_connection
    from backend.shared.billing_store import get_or_create_user,ensure_billing_tables
    await ensure_billing_tables()
    owner=get_or_create_user(f'{uuid4().hex}@fixture.invalid')['id']
    sid=str(uuid4())
    with get_connection() as conn:
        conn.execute("INSERT INTO sessions(id,user_id,status) VALUES (%s,%s,'completed')",(sid,owner))
        conn.commit()
    application_store.record_result(sid,'fixture-job','failed',error_category='submission_uncertain',user_id=owner)
    rows=application_store.get_results_for_session(sid)
    assert rows[-1]['error_category']=='submission_uncertain'
