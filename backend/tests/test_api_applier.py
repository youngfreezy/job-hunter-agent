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
    @pytest.mark.asyncio
    @patch("backend.browser.tools.api_applier.aiohttp.ClientSession")
    async def test_success_200(self, mock_cls):
        """Greenhouse API returns 200 — application submitted."""
        mock_cls.return_value = _mock_session(
            get_responses=[_mock_aiohttp_response(200, json_data={"questions": []})],
            post_responses=[_mock_aiohttp_response(200, text_data='{"success": true}')],
        )()

        job = _make_job(ATSType.GREENHOUSE, url="https://boards.greenhouse.io/anthropic/jobs/12345")
        result = await apply_via_api(
            job, {"name": "Test User", "email": "test@test.com"},
            "Resume text", "Cover letter", None, "session-1",
        )
        assert result is not None
        assert result.status == ApplicationStatus.SUBMITTED
        assert result.ats_type == "greenhouse_api"

    @pytest.mark.asyncio
    @patch("backend.browser.tools.api_applier.aiohttp.ClientSession")
    async def test_recaptcha_428_returns_none(self, mock_cls):
        """Greenhouse API returns 428 (reCAPTCHA) — should return None for Skyvern fallback."""
        mock_cls.return_value = _mock_session(
            get_responses=[_mock_aiohttp_response(200, json_data={"questions": []})],
            post_responses=[_mock_aiohttp_response(428, text_data="reCAPTCHA required")],
        )()

        job = _make_job(ATSType.GREENHOUSE, url="https://boards.greenhouse.io/stripe/jobs/67890")
        result = await apply_via_api(
            job, {"name": "Test"}, "", "", None, "session-1",
        )
        assert result is None

    @pytest.mark.asyncio
    @patch("backend.browser.tools.api_applier.aiohttp.ClientSession")
    async def test_validation_422_returns_failed(self, mock_cls):
        """Greenhouse API returns 422 — definitive failure, no fallback."""
        mock_cls.return_value = _mock_session(
            get_responses=[_mock_aiohttp_response(200, json_data={"questions": []})],
            post_responses=[_mock_aiohttp_response(422, text_data='{"errors": ["email required"]}')],
        )()

        job = _make_job(ATSType.GREENHOUSE, url="https://boards.greenhouse.io/acme/jobs/99999")
        result = await apply_via_api(job, {}, "", "", None, "session-1")
        assert result is not None
        assert result.status == ApplicationStatus.FAILED
        assert "validation error" in result.error_message.lower()

    @pytest.mark.asyncio
    @patch("backend.browser.tools.api_applier.aiohttp.ClientSession")
    async def test_job_not_found_404(self, mock_cls):
        """Greenhouse API returns 404 for job schema — job expired."""
        mock_cls.return_value = _mock_session(
            get_responses=[_mock_aiohttp_response(404)],
        )()

        job = _make_job(ATSType.GREENHOUSE, url="https://boards.greenhouse.io/gone/jobs/11111")
        result = await apply_via_api(job, {}, "", "", None, "session-1")
        assert result is not None
        assert result.status == ApplicationStatus.FAILED
        assert "not found" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_unparseable_url_returns_none(self):
        """Greenhouse job with non-standard URL — can't parse, return None."""
        job = _make_job(ATSType.GREENHOUSE, url="https://example.com/careers/apply")
        result = await apply_via_api(job, {}, "", "", None, "session-1")
        assert result is None


# ---------------------------------------------------------------------------
# Lever API tests (mocked HTTP)
# ---------------------------------------------------------------------------


class TestLeverApi:
    @pytest.mark.asyncio
    @patch("backend.browser.tools.api_applier.aiohttp.ClientSession")
    async def test_success_200(self, mock_cls):
        """Lever API returns 200 — application submitted."""
        mock_cls.return_value = _mock_session(
            post_responses=[_mock_aiohttp_response(200, text_data='{"ok": true}')],
        )()

        job = _make_job(ATSType.LEVER, url="https://jobs.lever.co/openai/abc-def-123")
        result = await apply_via_api(
            job, {"name": "Test User", "email": "test@test.com"},
            "Resume text", "Cover letter", None, "session-1",
        )
        assert result is not None
        assert result.status == ApplicationStatus.SUBMITTED
        assert result.ats_type == "lever_api"

    @pytest.mark.asyncio
    @patch("backend.browser.tools.api_applier.aiohttp.ClientSession")
    async def test_404_returns_failed(self, mock_cls):
        """Lever API returns 404 — job expired."""
        mock_cls.return_value = _mock_session(
            post_responses=[_mock_aiohttp_response(404, text_data="Not found")],
        )()

        job = _make_job(ATSType.LEVER, url="https://jobs.lever.co/oldcompany/dead-uuid")
        result = await apply_via_api(job, {}, "", "", None, "session-1")
        assert result is not None
        assert result.status == ApplicationStatus.FAILED

    @pytest.mark.asyncio
    @patch("backend.browser.tools.api_applier.aiohttp.ClientSession")
    async def test_500_returns_none_for_fallback(self, mock_cls):
        """Lever API returns 500 — return None for Skyvern fallback."""
        mock_cls.return_value = _mock_session(
            post_responses=[_mock_aiohttp_response(500, text_data="Internal error")],
        )()

        job = _make_job(ATSType.LEVER, url="https://jobs.lever.co/buggy/abc-123")
        result = await apply_via_api(job, {}, "", "", None, "session-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_unparseable_lever_url_returns_none(self):
        job = _make_job(ATSType.LEVER, url="https://example.com/careers")
        result = await apply_via_api(job, {}, "", "", None, "session-1")
        assert result is None
