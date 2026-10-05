"""Reruns retain the original scope and request a fresh discovery review."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.gateway.routes import sessions
from backend.shared import session_store, resume_store, task_queue


@pytest.fixture
def rerun(monkeypatch):
    from backend.gateway import deps
    state = {
        "keywords": ["AI engineer"], "locations": ["San Francisco"],
        "remote_only": False, "salary_min": 220000, "search_radius": 25,
        "resume_text": "Canonical Applicant\n" + "Verified experience. " * 30,
        "linkedin_url": "https://linkedin.com/in/example",
        "session_config": {"max_jobs": 1, "minimum_submitted_applications": 0,
                           "job_boards": ["indeed"], "application_mode": "auto_apply",
                           "discovery_mode": "manual_urls", "job_urls": ["https://www.indeed.com/viewjob?jk=unique"]},
        "job_urls": ["https://www.indeed.com/viewjob?jk=unique"],
        "preferences": {"discovery_prompt": "Only SF remote AI roles", "search_input_mode": "structured",
                        "_skip_coach_review": True, "_autopilot_auto_approve": True,
                        "_autopilot_schedule_id": "old-schedule"},
    }
    original = {"user_id": "owner", "status": "completed", "resume_text_snippet": "Truncated",
                "keywords": state["keywords"], "locations": state["locations"],
                "remote_only": False, "salary_min": 220000}
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values=state)))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(graph=graph)))
    monkeypatch.setattr(deps, "get_model_user", lambda _: {"id": "owner"})
    monkeypatch.setattr(session_store, "get_session_by_id", lambda _: original)
    monkeypatch.setattr(resume_store, "get_resume", lambda _: None)
    monkeypatch.setattr(task_queue, "enqueue_session", AsyncMock(return_value=True))
    monkeypatch.setattr(task_queue, "mark_active", AsyncMock())
    monkeypatch.setattr(sessions, "upsert_session", MagicMock())
    monkeypatch.setattr(sessions, "_spawn_background", lambda coro: coro.close())
    start = AsyncMock(return_value={"session_id": "new"})
    monkeypatch.setattr(sessions, "start_session", start)
    return request, state, original, start


@pytest.mark.asyncio
async def test_manual_rerun_preserves_one_url_config_and_full_resume(rerun):
    request, state, original, start = rerun
    await sessions.rerun_session("old", sessions.RerunRequest(), request)
    start.assert_awaited_once()
    body = start.await_args.args[0]
    assert body.job_urls == state["job_urls"]
    assert body.config.max_jobs == 1
    assert body.config.discovery_mode == "manual_urls"
    assert body.config.job_urls == state["job_urls"]
    assert body.resume_text == state["resume_text"]
    assert body.resume_uuid == "old"
    assert body.search_radius == 25
    assert body.preferences == {"discovery_prompt": "Only SF remote AI roles", "search_input_mode": "structured"}
    assert state["preferences"]["_autopilot_auto_approve"] is True


@pytest.mark.asyncio
async def test_search_rerun_applies_explicit_overrides_without_skipping_reviews(rerun):
    request, state, original, start = rerun
    state["job_urls"] = []
    state["session_config"].update(discovery_mode="ai_search", job_urls=[], application_mode="materials_only")
    await sessions.rerun_session("old", sessions.RerunRequest(keywords=["Applied AI"], remote_only=True), request)
    body = start.await_args.args[0]
    assert body.keywords == ["Applied AI"] and body.remote_only is True
    assert body.locations == ["San Francisco"] and body.salary_min == 220000
    assert body.config.application_mode == "materials_only" and body.config.max_jobs == 1
    assert "_skip_coach_review" not in body.preferences
    assert "_autopilot_auto_approve" not in body.preferences


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["missing_snapshot", "active", "missing_config", "empty_config", "wrong_owner"])
async def test_incomplete_or_unauthorized_rerun_does_not_launch(rerun, invalid):
    request, state, original, start = rerun
    if invalid == "missing_snapshot":
        request.app.state.graph.aget_state.return_value = SimpleNamespace(values={})
    elif invalid == "active": original["status"] = "applying"
    elif invalid == "missing_config": state.pop("session_config")
    elif invalid == "empty_config": state["session_config"] = None
    else: original["user_id"] = "someone-else"
    with pytest.raises(HTTPException) as error:
        await sessions.rerun_session("old", sessions.RerunRequest(), request)
    assert error.value.status_code == (403 if invalid == "wrong_owner" else 409)
    start.assert_not_awaited()


@pytest.mark.asyncio
async def test_rerun_accepts_config_model_written_by_backfill(rerun):
    from backend.shared.models.schemas import SessionConfig
    request, state, original, start = rerun
    state["session_config"] = SessionConfig(**state["session_config"])
    await sessions.rerun_session("old", sessions.RerunRequest(), request)
    body = start.await_args.args[0]
    assert body.config.max_jobs == 1
    assert body.job_urls == state["job_urls"]
