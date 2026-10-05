"""Unknown POST delivery must not cross the browser-fallback boundary."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.browser.tools import api_applier
from backend.shared.models.schemas import ApplicationErrorCategory, ATSType, JobBoard, JobListing


@pytest.fixture
def api_transport(monkeypatch):
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    schema = MagicMock(status=200)
    schema.json = AsyncMock(return_value={"questions": []})
    schema.__aenter__ = AsyncMock(return_value=schema)
    schema.__aexit__ = AsyncMock(return_value=False)
    session.get.return_value = schema
    response = MagicMock()
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    response.text = AsyncMock(return_value="response")
    session.post.return_value = response
    monkeypatch.setattr(api_applier.aiohttp, "ClientSession", lambda: session)
    monkeypatch.setattr(api_applier, "_read_resume_bytes", lambda _: None)
    monkeypatch.setattr(api_applier, "_answer_greenhouse_questions", AsyncMock(return_value={}))
    return session, response


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["greenhouse", "lever"])
@pytest.mark.parametrize("failure", ["timeout", "bad_gateway", "unrecognized_success"])
async def test_unknown_post_delivery_is_a_durable_hold(api_transport, provider, failure):
    session, response = api_transport
    if failure == "timeout":
        response.__aenter__.side_effect = asyncio.TimeoutError()
    else:
        response.status = 502 if failure == "bad_gateway" else 202
    url = ("https://boards.greenhouse.io/acme/jobs/123" if provider == "greenhouse"
           else "https://jobs.lever.co/acme/abc-def")
    job = JobListing(id="job", title="Engineer", company="Acme", location="Remote",
                     url=url, board=JobBoard.INDEED, ats_type=ATSType(provider))
    result = await getattr(api_applier, f"_apply_{provider}")(job, {}, "resume", "", None, "session")
    assert result is not None
    assert result.error_category is ApplicationErrorCategory.SUBMISSION_UNCERTAIN
    assert result.failure_step == "submit"
    session.post.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 428, 429])
async def test_explicit_greenhouse_rejection_still_permits_browser_fallback(api_transport, status):
    _, response = api_transport
    response.status = status
    job = JobListing(id="job", title="Engineer", company="Acme", location="Remote",
                     url="https://boards.greenhouse.io/acme/jobs/123", board=JobBoard.INDEED)
    assert await api_applier._apply_greenhouse(job, {}, "resume", "", None, "session") is None
