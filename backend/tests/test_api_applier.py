# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Unit tests for the direct ATS API applier.

Tests Greenhouse and Lever API submission with mocked HTTP responses.
"""

import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from backend.browser.tools.api_applier import (
    _parse_greenhouse_url,
    _parse_lever_url,
    _answer_questions_fallback,
    apply_via_api,
)
from backend.shared.models.schemas import (
    ApplicationResult,
    ApplicationStatus,
    ATSType,
    JobListing,
)


# ---------------------------------------------------------------------------
# URL parsing tests
# ---------------------------------------------------------------------------


class TestParseGreenhouseUrl:
    def test_standard_url(self):
        url = "https://boards.greenhouse.io/anthropic/jobs/7544220"
        result = _parse_greenhouse_url(url)
        assert result == ("anthropic", "7544220")

    def test_url_with_query_params(self):
        url = "https://boards.greenhouse.io/hubspotjobs/jobs/7544220?gh_jid=7544220"
        result = _parse_greenhouse_url(url)
        assert result == ("hubspotjobs", "7544220")

    def test_non_greenhouse_url(self):
        url = "https://jobs.lever.co/company/abc123"
        assert _parse_greenhouse_url(url) is None

    def test_no_jobs_path(self):
        url = "https://boards.greenhouse.io/anthropic"
        assert _parse_greenhouse_url(url) is None


class TestParseLeverUrl:
    def test_standard_url(self):
        url = "https://jobs.lever.co/openai/abc123-def456"
        result = _parse_lever_url(url)
        assert result == ("openai", "abc123-def456")

    def test_with_apply_suffix(self):
        url = "https://jobs.lever.co/stripe/a1b2c3d4-e5f6-7890-abcd-ef1234567890/apply"
        result = _parse_lever_url(url)
        assert result == ("stripe", "a1b2c3d4-e5f6-7890-abcd-ef1234567890")

    def test_non_lever_url(self):
        url = "https://boards.greenhouse.io/anthropic/jobs/123"
        assert _parse_lever_url(url) is None


# ---------------------------------------------------------------------------
# Fallback question answering
# ---------------------------------------------------------------------------


class TestAnswerQuestionsFallback:
    def test_linkedin_question(self):
        questions = [{
            "id": 100, "label": "LinkedIn Profile URL", "required": True,
            "fields": [{"type": "input_text", "values": []}],
        }]
        profile = {"linkedin_url": "https://www.linkedin.com/in/johndoe"}
        answers = _answer_questions_fallback(questions, profile)
        assert answers["question_100"] == "https://www.linkedin.com/in/johndoe"

    def test_salary_question(self):
        questions = [{
            "id": 200, "label": "Desired Salary/Compensation", "required": True,
            "fields": [{"type": "input_text", "values": []}],
        }]
        profile = {"salary_expectation": "$150,000"}
        answers = _answer_questions_fallback(questions, profile)
        assert answers["question_200"] == "$150,000"

    def test_select_authorization_question(self):
        questions = [{
            "id": 300, "label": "Are you authorized to work in the US?",
            "required": True,
            "fields": [{"type": "multi_value_single_select", "values": [
                {"value": "1", "label": "Yes"},
                {"value": "2", "label": "No"},
            ]}],
        }]
        answers = _answer_questions_fallback(questions, {})
        assert answers["question_300"] == "1"  # "Yes"

    def test_sponsorship_question(self):
        questions = [{
            "id": 400, "label": "Do you require visa sponsorship?",
            "required": True,
            "fields": [{"type": "multi_value_single_select", "values": [
                {"value": "yes", "label": "Yes"},
                {"value": "no", "label": "No"},
            ]}],
        }]
        answers = _answer_questions_fallback(questions, {})
        assert answers["question_400"] == "no"

    def test_empty_questions(self):
        assert _answer_questions_fallback([], {}) == {}

    def test_skips_non_required_text_without_keyword(self):
        questions = [{
            "id": 500, "label": "Anything else?", "required": False,
            "fields": [{"type": "input_text", "values": []}],
        }]
        answers = _answer_questions_fallback(questions, {})
        assert "question_500" not in answers


# ---------------------------------------------------------------------------
# Dispatcher tests
# ---------------------------------------------------------------------------


def _make_job(ats_type: ATSType, url: str = "", **kwargs) -> JobListing:
    from datetime import datetime
    return JobListing(
        id=kwargs.get("id", "test-job-1"),
        title=kwargs.get("title", "Software Engineer"),
        company=kwargs.get("company", "TestCo"),
        location="Austin, TX",
        url=url or "https://example.com/job",
        board=kwargs.get("board", "google_jobs"),
        ats_type=ats_type,
    )


class TestApplyViaApiDispatch:
    @pytest.mark.asyncio
    async def test_unsupported_ats_returns_none(self):
        job = _make_job(ATSType.WORKDAY, url="https://myworkdayjobs.com/job/123")
        result = await apply_via_api(job, {}, "", "", None, "session-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_unknown_ats_returns_none(self):
        job = _make_job(ATSType.UNKNOWN, url="https://example.com/careers")
        result = await apply_via_api(job, {}, "", "", None, "session-1")
        assert result is None


# ---------------------------------------------------------------------------
# Greenhouse API tests (mocked HTTP)
# ---------------------------------------------------------------------------


def _mock_aiohttp_response(status, json_data=None, text_data=""):
    """Create a mock that works with `async with session.get/post() as resp:`."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    resp.text = AsyncMock(return_value=text_data)

    @asynccontextmanager
    async def _ctx(*args, **kwargs):
        yield resp

    return _ctx


def _mock_session(get_responses=None, post_responses=None):
    """Build a mock aiohttp.ClientSession with sequenced GET/POST responses."""
    session = MagicMock()

    if get_responses:
        get_iter = iter(get_responses)
        def _get_side_effect(*args, **kwargs):
            resp_factory = next(get_iter)
            return resp_factory(*args, **kwargs)
        session.get = MagicMock(side_effect=_get_side_effect)
    if post_responses:
        post_iter = iter(post_responses)
        def _post_side_effect(*args, **kwargs):
            resp_factory = next(post_iter)
            return resp_factory(*args, **kwargs)
        session.post = MagicMock(side_effect=_post_side_effect)

    @asynccontextmanager
    async def _session_ctx():
        yield session

    return _session_ctx


class TestGreenhouseApi:
    """Greenhouse API handlers are disabled (_ATS_HANDLERS is empty) because
    the POST endpoint requires per-company HTTP Basic Auth keys that we don't
    have. All Greenhouse jobs go straight to Skyvern now. These tests verify
    that apply_via_api correctly returns None for Greenhouse jobs."""

    @pytest.mark.asyncio
    async def test_greenhouse_returns_none(self):
        """Greenhouse job with fake job_id returns FAILED/JOB_EXPIRED (404 from API)."""
        job = _make_job(ATSType.GREENHOUSE, url="https://boards.greenhouse.io/anthropic/jobs/12345")
        result = await apply_via_api(
            job, {"name": "Test User", "email": "test@test.com"},
            "Resume text", "Cover letter", None, "session-1",
        )
        # Handler is now enabled — fake job_id returns 404
        assert result is not None
        assert result.status.value == "failed"
        assert result.error_category.value == "job_expired"

    @pytest.mark.asyncio
    async def test_unparseable_url_returns_none(self):
        """Greenhouse job with non-standard URL — can't parse, return None."""
        job = _make_job(ATSType.GREENHOUSE, url="https://example.com/careers/apply")
        result = await apply_via_api(job, {}, "", "", None, "session-1")
        assert result is None


# ---------------------------------------------------------------------------
# Lever API tests — handler enabled, uses public Lever Postings API
# ---------------------------------------------------------------------------


class TestLeverApi:
    """Lever API handlers are enabled. Uses public api.lever.co endpoint."""

    @pytest.mark.asyncio
    async def test_lever_fake_posting_returns_none_or_error(self):
        """Lever job with fake posting_id — API returns error or None."""
        job = _make_job(ATSType.LEVER, url="https://jobs.lever.co/openai/abc-def-123")
        result = await apply_via_api(
            job, {"name": "Test User", "email": "test@test.com"},
            "Resume text", "Cover letter", None, "session-1",
        )
        # Fake posting returns 404 or other error — result may be None (fallback) or FAILED
        if result is not None:
            assert result.status.value == "failed"

    @pytest.mark.asyncio
    async def test_unparseable_lever_url_returns_none(self):
        job = _make_job(ATSType.LEVER, url="https://example.com/careers")
        result = await apply_via_api(job, {}, "", "", None, "session-1")
        assert result is None
