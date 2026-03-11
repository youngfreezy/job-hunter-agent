# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Unit tests for URL validation at shortlist review."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from backend.orchestrator.pipeline.graph import _validate_job_urls


def _make_scored_job(url: str, title: str = "Engineer", score: int = 80):
    """Create a mock ScoredJob with the given URL."""
    job = MagicMock()
    job.url = url
    job.title = title
    sj = MagicMock()
    sj.job = job
    sj.score = score
    return sj


class TestValidateJobUrls:
    """Tests for _validate_job_urls."""

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self):
        result = await _validate_job_urls([], "test-session")
        assert result == []

    @pytest.mark.asyncio
    async def test_filters_out_404_urls(self):
        sj_good = _make_scored_job("https://example.com/job/1", "Good Job")
        sj_dead = _make_scored_job("https://example.com/job/2", "Dead Job")

        mock_responses = {
            "https://example.com/job/1": 200,
            "https://example.com/job/2": 404,
        }

        async def mock_head(url, **kwargs):
            resp = MagicMock()
            resp.status_code = mock_responses.get(url, 200)
            return resp

        with patch("backend.orchestrator.pipeline.graph.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.head = mock_head
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            result = await _validate_job_urls([sj_good, sj_dead], "test-session")

        assert len(result) == 1
        assert result[0] is sj_good

    @pytest.mark.asyncio
    async def test_filters_out_unreachable_urls(self):
        sj_good = _make_scored_job("https://example.com/job/1")
        sj_unreachable = _make_scored_job("https://dead-host.invalid/job/2")

        async def mock_head(url, **kwargs):
            if "dead-host" in url:
                raise ConnectionError("DNS resolution failed")
            resp = MagicMock()
            resp.status_code = 200
            return resp

        with patch("backend.orchestrator.pipeline.graph.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.head = mock_head
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            result = await _validate_job_urls([sj_good, sj_unreachable], "test-session")

        assert len(result) == 1
        assert result[0] is sj_good

    @pytest.mark.asyncio
    async def test_falls_back_to_get_on_405(self):
        sj = _make_scored_job("https://example.com/job/1")

        call_count = {"head": 0, "get": 0}

        async def mock_head(url, **kwargs):
            call_count["head"] += 1
            resp = MagicMock()
            resp.status_code = 405
            return resp

        async def mock_get(url, **kwargs):
            call_count["get"] += 1
            resp = MagicMock()
            resp.status_code = 200
            return resp

        with patch("backend.orchestrator.pipeline.graph.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.head = mock_head
            client_instance.get = mock_get
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            result = await _validate_job_urls([sj], "test-session")

        assert len(result) == 1
        assert call_count["head"] == 1
        assert call_count["get"] == 1

    @pytest.mark.asyncio
    async def test_keeps_all_valid_urls(self):
        jobs = [_make_scored_job(f"https://example.com/job/{i}") for i in range(5)]

        async def mock_head(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            return resp

        with patch("backend.orchestrator.pipeline.graph.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.head = mock_head
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            result = await _validate_job_urls(jobs, "test-session")

        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_empty_url_filtered_out(self):
        sj = _make_scored_job("", "No URL Job")

        result = await _validate_job_urls([sj], "test-session")

        assert len(result) == 0
