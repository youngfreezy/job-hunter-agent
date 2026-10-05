"""Default runs keep applications on the guarded browser path."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.orchestrator.agents import application
from backend.shared.config import Settings, settings
from backend.shared.models.schemas import ApplicationResult, ApplicationStatus, ATSType, JobBoard, JobListing


@pytest.mark.asyncio
async def test_default_configuration_does_not_route_to_experimental_direct_api(monkeypatch):
    monkeypatch.delenv("API_APPLY_ENABLED", raising=False)
    default = Settings(_env_file=None).API_APPLY_ENABLED
    monkeypatch.setattr(settings, "API_APPLY_ENABLED", default)
    monkeypatch.setattr(settings, "INDEED_ONLY", False)
    monkeypatch.setattr(settings, "INDEED_EASY_APPLY_ONLY", False)
    monkeypatch.setattr(application, "emit_agent_event", AsyncMock())
    context = object()
    manager = SimpleNamespace(
        stagehand=None, live_view_url=None, browserbase_session_id=None,
        start_for_task=AsyncMock(), new_context=AsyncMock(return_value=("context", context)),
        stop=AsyncMock(),
    )
    monkeypatch.setattr(application, "BrowserManager", lambda: manager)
    apply = AsyncMock(return_value=ApplicationResult(job_id="greenhouse", status=ApplicationStatus.SKIPPED))
    monkeypatch.setattr(application, "_apply_to_job", apply)
    job = JobListing(id="greenhouse", title="Engineer", company="Acme", location="Remote",
                     url="https://boards.greenhouse.io/acme/jobs/1", board=JobBoard.OTHER,
                     ats_type=ATSType.GREENHOUSE)
    await application.run_application_agent({
        "session_id": "test", "application_queue": [job.id], "discovered_jobs": [job],
    })
    assert default is False
    assert apply.await_args.kwargs["context"] is context
    manager.stop.assert_awaited_once()
