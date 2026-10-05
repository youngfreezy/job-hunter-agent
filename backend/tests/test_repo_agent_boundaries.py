"""Regression coverage for agent URL boundaries and steering delivery."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.browser.tools.ats_detector import detect_ats_from_url, detect_ats_type
from backend.orchestrator.agents.url_hydrator import _detect_ats
from backend.shared.models.schemas import ATSType, JobBoard


@pytest.mark.parametrize("url", [
    "https://careers.example.com/?next=https://jobs.lever.co/acme/123",
    "https://notgreenhouse.io/jobs/123",
    "https://greenhouse.io.example.com/acme/jobs/123",
    "https://jobs.lever.co@careers.example.com/jobs/123",
    "https://careers.example.com/path/indeed.com/viewjob",
    "https://notlinkedin.com/jobs/123",
])
def test_ats_detection_uses_hostname_boundaries(url):
    assert detect_ats_from_url(url) is ATSType.UNKNOWN
    assert _detect_ats(url) == (ATSType.UNKNOWN, JobBoard.OTHER)


@pytest.mark.parametrize("url, expected", [
    ("https://www.indeed.com/viewjob?jk=abc", ATSType.INDEED),
    ("https://job-boards.greenhouse.io/acme/jobs/123", ATSType.GREENHOUSE),
    ("https://jobs.lever.co/acme/123", ATSType.LEVER),
    ("https://acme.wd1.myworkdayjobs.com/careers/123", ATSType.WORKDAY),
    ("https://careers-acme.icims.com/jobs/123", ATSType.ICIMS),
    ("https://acme.taleo.net/careersection/jobdetail.ftl", ATSType.TALEO),
])
def test_ats_detection_preserves_supported_hosts(url, expected):
    assert detect_ats_from_url(url) is expected


@pytest.mark.asyncio
async def test_browser_detection_uses_same_hostname_policy():
    page = SimpleNamespace(
        url="https://careers.example.com/?next=https://jobs.lever.co/acme/123",
        evaluate=AsyncMock(return_value={}),
    )
    assert await detect_ats_type(page) is ATSType.UNKNOWN


class SteeringRedis:
    """A queued command arrives at the first asynchronous Redis boundary."""

    def __init__(self):
        self.messages = ["skip this job"]
        self.close = AsyncMock()
        self.aclose = AsyncMock()

    async def lrange(self, *_args):
        old = self.messages.copy()
        self.messages.append("pause")
        return old

    async def delete(self, *_args):
        self.messages.clear()

    def pipeline(self, *, transaction):
        assert transaction
        redis = self

        class Pipeline:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            def lrange(self, *_args):
                return self

            def delete(self, *_args):
                return self

            async def execute(self):
                return await redis.execute()

        return Pipeline()

    async def execute(self):
        old = self.messages.copy()
        self.messages.clear()
        self.messages.append("pause")
        return [old, 1]


@pytest.mark.asyncio
async def test_steering_drain_preserves_commands_arriving_after_atomic_read(monkeypatch):
    from backend.orchestrator.agents.application import _drain_steering_commands

    redis = SteeringRedis()
    monkeypatch.setattr("redis.asyncio.from_url", lambda *_a, **_k: redis)
    assert await _drain_steering_commands("session") == ["skip this job"]
    assert redis.messages == ["pause"]
    redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_steering_drain_closes_connection_after_redis_failure(monkeypatch):
    from backend.orchestrator.agents.application import _drain_steering_commands

    redis = SteeringRedis()
    redis.execute = AsyncMock(side_effect=OSError("Redis unavailable"))
    redis.lrange = AsyncMock(side_effect=OSError("Redis unavailable"))
    monkeypatch.setattr("redis.asyncio.from_url", lambda *_a, **_k: redis)
    assert await _drain_steering_commands("session") == []
    redis.aclose.assert_awaited_once()
