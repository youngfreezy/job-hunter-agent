from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.browser.tools import indeed_hydration as module
from backend.orchestrator.agents.intake import run_intake_agent
from backend.orchestrator.pipeline.graph import _validate_job_urls, intake_node
from backend.shared.config import settings

URL = "https://www.indeed.com/viewjob?jk=example"


@pytest.fixture
def cloud(monkeypatch):
    page = SimpleNamespace(goto=AsyncMock(), wait_for_function=AsyncMock())
    stage_page = SimpleNamespace(url=AsyncMock(return_value=URL))
    manager = MagicMock()
    manager.start_for_task = AsyncMock()
    manager.new_context = AsyncMock(return_value=("ctx", SimpleNamespace(pages=[page])))
    manager.stop = AsyncMock()
    manager.stagehand.browser.context.active_page = AsyncMock(return_value=stage_page)
    manager.stagehand.extract = AsyncMock(return_value=SimpleNamespace(data=module.IndeedListing(
        title="Applied AI Engineer", company="Example", location="Remote in San Francisco",
        description="Build AI software", is_remote=True, can_apply_on_indeed=True,
        expired=False, blocked=False,
    )))
    monkeypatch.setattr(module, "BrowserManager", lambda: manager)
    monkeypatch.setattr(module, "emit_agent_event", AsyncMock())
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    return manager


@pytest.mark.asyncio
async def test_quick_apply_reads_listing_in_owner_cloud_context(monkeypatch, cloud):
    monkeypatch.setattr(settings, "INDEED_ONLY", True)
    http = AsyncMock(side_effect=AssertionError("No anonymous Indeed requests"))
    monkeypatch.setattr("backend.orchestrator.agents.url_hydrator.hydrate_urls", http)
    result = await run_intake_agent({"job_urls": [URL], "user_id": "owner", "session_id": "session"})
    job = result["discovered_jobs"][0]
    assert job.title == "Applied AI Engineer"
    assert job.company == "Example"
    assert job.verified_open
    cloud.start_for_task.assert_awaited_once_with(board=module.JobBoard.INDEED, purpose="hydrate", user_id="owner")
    cloud.stop.assert_awaited_once()
    http.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["blocked", "expired"])
async def test_unavailable_listing_fails_without_fabricated_job(cloud, field):
    setattr(cloud.stagehand.extract.return_value.data, field, True)
    with pytest.raises(ValueError):
        await module.hydrate_indeed_urls([URL], user_id="owner", session_id="session")
    cloud.stop.assert_awaited_once()
    assert module.emit_agent_event.await_args.args[1] == "browser_live_view_ended"


@pytest.mark.asyncio
async def test_unknown_apply_destination_is_checked_by_application_browser(cloud):
    cloud.stagehand.extract.return_value.data.can_apply_on_indeed = False
    jobs = await module.hydrate_indeed_urls([URL], user_id="owner", session_id="session")
    assert jobs[0].url == URL
    assert not jobs[0].is_easy_apply
    assert not jobs[0].verified_open


@pytest.mark.asyncio
async def test_rejects_external_url_before_starting_cloud(cloud):
    with pytest.raises(ValueError):
        await module.hydrate_indeed_urls(["https://indeed.com.evil.test/"], user_id="owner", session_id="session")
    cloud.start_for_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_managed_challenge_can_clear_before_listing_extraction(cloud):
    good = cloud.stagehand.extract.return_value
    blocked = SimpleNamespace(data=good.data.model_copy(update={"blocked": True}))
    cloud.stagehand.extract.side_effect = [blocked, good]
    jobs = await module.hydrate_indeed_urls([URL], user_id="owner", session_id="session")
    assert len(jobs) == 1
    module.asyncio.sleep.assert_awaited_once_with(10)
    cloud.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_listing_validation_never_sends_anonymous_indeed_probe(monkeypatch):
    monkeypatch.setattr(settings, "INDEED_ONLY", True)
    client = MagicMock(side_effect=AssertionError("No anonymous HTTP probes"))
    monkeypatch.setattr("backend.orchestrator.pipeline.graph.httpx.AsyncClient", client)
    job = SimpleNamespace(job=SimpleNamespace(url=URL, title="Engineer"))
    external = SimpleNamespace(job=SimpleNamespace(url="https://indeed.com.evil.test/", title="Bad"))
    assert await _validate_job_urls([job, external]) == [job]
    client.assert_not_called()


@pytest.mark.asyncio
async def test_unreadable_quick_apply_stops_before_other_pipeline_stages(monkeypatch, cloud):
    monkeypatch.setattr(settings, "INDEED_ONLY", True)
    cloud.stagehand.extract.return_value.data.blocked = True
    with pytest.raises(RuntimeError, match="Check your saved Indeed login"):
        await intake_node({"job_urls": [URL], "user_id": "owner", "session_id": "session"})
    cloud.stop.assert_awaited_once()
