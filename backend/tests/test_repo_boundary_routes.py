"""Public error responses and account-erasure orchestration honor boundaries."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_resume_analysis_does_not_expose_provider_exception(monkeypatch):
    from backend.gateway.routes import resume
    monkeypatch.setattr(resume, "get_model_user", lambda _: {"id": "owner"})
    monkeypatch.setattr(resume, "build_llm", MagicMock(side_effect=RuntimeError("api_key=secret-private-data")))
    with pytest.raises(HTTPException) as error:
        await resume.analyze_resume(resume.ResumeAnalyzeRequest(resume_text="Resume experience. " * 10), None)
    assert error.value.status_code == 500
    assert "secret-private-data" not in error.value.detail


@pytest.fixture
def account_route(monkeypatch):
    from backend.gateway.routes import auth, sessions
    from backend.shared import billing_store, model_key_store, session_store
    from backend.shared.redis_client import redis_client
    monkeypatch.setattr(auth, "get_current_user", lambda _: {"id": "owner", "email": "private@example.com"})
    monkeypatch.setattr(model_key_store, "save_model_key", MagicMock())
    monkeypatch.setattr(session_store, "get_session_ids_for_user", MagicMock(return_value=["persisted"]))
    monkeypatch.setattr("backend.shared.task_queue.get_user_active_count", AsyncMock(return_value=0))
    monkeypatch.setattr(sessions, "session_registry", {"memory": {"user_id": "owner"}})
    monkeypatch.setattr(redis_client, "delete", AsyncMock(return_value=1))
    # Only the public API of Redis is exercised; there are no real connections.
    redis = MagicMock()
    redis.delete = AsyncMock(return_value=0)
    monkeypatch.setattr(redis_client, "_redis", redis)
    deletion = MagicMock(return_value=True)
    monkeypatch.setattr(billing_store, "delete_user_data", deletion)
    return auth, sessions, deletion, redis_client


@pytest.mark.asyncio
async def test_account_deletion_uses_persisted_sessions_after_restart(account_route):
    auth, sessions, _, redis = account_route
    response = await auth.delete_user_data(None)
    assert response.status_code == 200
    assert json.loads(response.body)["sessions_cleared"] == 2
    redis.delete.assert_any_await("gmail_token:persisted")
    assert sessions.session_registry == {}


@pytest.mark.asyncio
async def test_account_db_failure_does_not_claim_success_or_clear_memory(account_route):
    auth, sessions, deletion, redis = account_route
    deletion.return_value = False
    with pytest.raises(HTTPException) as error:
        await auth.delete_user_data(None)
    assert error.value.status_code == 503
    assert "memory" in sessions.session_registry
    redis.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_account_deletion_rejects_queued_work_before_removing_keys(account_route, monkeypatch):
    from backend.shared import model_key_store
    auth, _, deletion, _ = account_route
    monkeypatch.setattr("backend.shared.task_queue.get_user_active_count", AsyncMock(return_value=1))
    with pytest.raises(HTTPException) as error:
        await auth.delete_user_data(None)
    assert error.value.status_code == 409
    model_key_store.save_model_key.assert_not_called()
    deletion.assert_not_called()


@pytest.mark.asyncio
async def test_account_deletion_rejects_unsettled_local_worker(account_route, monkeypatch):
    auth, _, deletion, _ = account_route
    monkeypatch.setattr("backend.shared.pipeline_guard.is_pipeline_active", lambda _: True)
    with pytest.raises(HTTPException) as error:
        await auth.delete_user_data(None)
    assert error.value.status_code == 409
    deletion.assert_not_called()


@pytest.mark.asyncio
async def test_account_deletion_stops_on_queue_outage(account_route, monkeypatch):
    from backend.shared import model_key_store
    auth, _, deletion, _ = account_route
    monkeypatch.setattr("backend.shared.task_queue.get_user_active_count", AsyncMock(side_effect=RuntimeError("offline")))
    with pytest.raises(HTTPException) as error:
        await auth.delete_user_data(None)
    assert error.value.status_code == 503
    model_key_store.save_model_key.assert_not_called()
    deletion.assert_not_called()


@pytest.mark.asyncio
async def test_session_deletion_verifies_owner_before_checking_queue(monkeypatch):
    from backend.gateway.routes import sessions
    monkeypatch.setattr("backend.gateway.deps.get_current_user", lambda _: {"id": "other"})
    monkeypatch.setattr("backend.gateway.deps.verify_session_owner", AsyncMock(side_effect=HTTPException(status_code=403)))
    queue = AsyncMock(return_value=0)
    monkeypatch.setattr("backend.shared.task_queue.get_queue_position", queue)
    with pytest.raises(HTTPException) as error:
        await sessions.delete_session_endpoint("owned", None)
    assert error.value.status_code == 403
    queue.assert_not_awaited()


@pytest.mark.asyncio
async def test_session_deletion_rejects_pending_admission_before_erasure(monkeypatch):
    from backend.gateway.routes import sessions
    monkeypatch.setattr("backend.gateway.deps.get_current_user", lambda _: {"id": "owner"})
    monkeypatch.setattr("backend.gateway.deps.verify_session_owner", AsyncMock())
    monkeypatch.setattr("backend.shared.task_queue.get_queue_position", AsyncMock(return_value=1))
    erase = MagicMock(return_value=True)
    monkeypatch.setattr("backend.shared.session_store.delete_session", erase)
    with pytest.raises(HTTPException) as error:
        await sessions.delete_session_endpoint("owned", None)
    assert error.value.status_code == 409
    erase.assert_not_called()
