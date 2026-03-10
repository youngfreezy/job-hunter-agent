# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Unit tests for salary extraction and payload flow.

Validates that salary_min from session state flows through:
1. _extract_user_profile → profile["salary_expectation"]
2. _build_navigation_payload → payload["salary_expectation"]
"""

import pytest

from backend.browser.tools.skyvern_applier import _build_navigation_payload


class TestBuildNavigationPayload:
    """Tests for _build_navigation_payload salary handling."""

    def test_includes_salary_expectation(self):
        profile = {"name": "John Doe", "email": "john@example.com", "salary_expectation": "$120,000"}
        payload = _build_navigation_payload(profile, "Resume text", "Cover letter")

        assert payload["salary_expectation"] == "$120,000"

    def test_no_salary_when_absent(self):
        profile = {"name": "John Doe", "email": "john@example.com"}
        payload = _build_navigation_payload(profile, "Resume text", "Cover letter")

        assert "salary_expectation" not in payload

    def test_splits_name_into_first_last(self):
        profile = {"name": "Jane Smith"}
        payload = _build_navigation_payload(profile, "", "")

        assert payload["first_name"] == "Jane"
        assert payload["last_name"] == "Smith"
        assert payload["full_name"] == "Jane Smith"

    def test_includes_all_profile_fields(self):
        profile = {
            "name": "Alice Wonder",
            "email": "alice@test.com",
            "phone": "555-1234",
            "location": "Austin, TX",
            "salary_expectation": "$95,000",
        }
        payload = _build_navigation_payload(profile, "Resume", "Cover")

        assert payload["email"] == "alice@test.com"
        assert payload["phone"] == "555-1234"
        assert payload["location"] == "Austin, TX"
        assert payload["salary_expectation"] == "$95,000"

    def test_resume_text_truncated(self):
        long_resume = "x" * 5000
        payload = _build_navigation_payload({}, long_resume, "")

        assert len(payload["resume_text"]) == 4000

    def test_resume_url_included(self):
        payload = _build_navigation_payload({}, "Resume", "", resume_file_url="https://example.com/resume.pdf")
        assert payload["resume_url"] == "https://example.com/resume.pdf"


class TestExtractUserProfileSalary:
    """Tests for salary extraction in _extract_user_profile."""

    @pytest.mark.asyncio
    async def test_salary_min_formatted(self):
        from backend.orchestrator.agents.application import _extract_user_profile

        state = {
            "resume_text": "John Doe\njohn@example.com\n555-1234",
            "salary_min": 120000,
        }
        profile = await _extract_user_profile(state)
        assert profile["salary_expectation"] == "$120,000"

    @pytest.mark.asyncio
    async def test_no_salary_when_not_set(self):
        from backend.orchestrator.agents.application import _extract_user_profile

        state = {
            "resume_text": "John Doe\njohn@example.com",
        }
        profile = await _extract_user_profile(state)
        assert "salary_expectation" not in profile

    @pytest.mark.asyncio
    async def test_salary_zero_excluded(self):
        from backend.orchestrator.agents.application import _extract_user_profile

        state = {
            "resume_text": "John Doe\njohn@example.com",
            "salary_min": 0,
        }
        profile = await _extract_user_profile(state)
        # 0 is falsy, so salary_expectation should not be set
        assert "salary_expectation" not in profile
