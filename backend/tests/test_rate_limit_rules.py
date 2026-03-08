"""Tests for rate limiting route classification rules."""

import re

from backend.gateway.middleware.rate_limit import _classify_request


class TestSessionCreateRateLimit:
    """Session creation must be limited to 2 requests per 60 seconds."""

    def test_session_create_classified(self):
        result = _classify_request("/api/sessions", "POST")
        assert result is not None
        max_req, window, bucket = result
        assert bucket == "session_create"

    def test_session_create_limit_is_2(self):
        max_req, window, bucket = _classify_request("/api/sessions", "POST")
        assert max_req == 2, f"Expected 2 req/min for session create, got {max_req}"
        assert window == 60

    def test_session_get_not_create_limit(self):
        """GET /api/sessions should hit general API limit, not session_create."""
        result = _classify_request("/api/sessions", "GET")
        assert result is not None
        _, _, bucket = result
        assert bucket != "session_create"


class TestTestApplyRateLimit:
    """/test-apply endpoint must have its own rate limit."""

    def test_test_apply_classified(self):
        result = _classify_request("/api/sessions/abc123/test-apply", "POST")
        assert result is not None
        max_req, window, bucket = result
        assert bucket == "test_apply"

    def test_test_apply_limit(self):
        max_req, window, bucket = _classify_request("/api/sessions/abc123/test-apply", "POST")
        assert max_req == 3
        assert window == 60


class TestCORSRestriction:
    """CORS regex must not match arbitrary vercel.app subdomains."""

    def test_cors_regex_matches_app_domain(self):
        pattern = r"https://job-hunter-agent(-[a-z0-9]+)?\.vercel\.app"
        assert re.fullmatch(pattern, "https://job-hunter-agent.vercel.app")

    def test_cors_regex_matches_preview_deploy(self):
        pattern = r"https://job-hunter-agent(-[a-z0-9]+)?\.vercel\.app"
        assert re.fullmatch(pattern, "https://job-hunter-agent-abc123.vercel.app")

    def test_cors_regex_rejects_evil_domain(self):
        pattern = r"https://job-hunter-agent(-[a-z0-9]+)?\.vercel\.app"
        assert not re.fullmatch(pattern, "https://evil.vercel.app")

    def test_cors_regex_rejects_arbitrary_subdomain(self):
        pattern = r"https://job-hunter-agent(-[a-z0-9]+)?\.vercel\.app"
        assert not re.fullmatch(pattern, "https://attacker-site.vercel.app")
