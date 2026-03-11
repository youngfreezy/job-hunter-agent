# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Tests for experience-level job filtering in the scoring agent.

Verifies that entry-level jobs (New Grad, Intern, etc.) are filtered out
when the candidate's experience level is senior or executive, and that
mid/entry candidates keep all jobs.
"""

import pytest
from backend.shared.models.schemas import JobListing
from backend.orchestrator.agents.scoring import filter_by_experience_level


def _make_job(title: str, **kwargs) -> JobListing:
    return JobListing(
        id=kwargs.get("id", "test-id"),
        title=title,
        company=kwargs.get("company", "TestCo"),
        url=kwargs.get("url", "https://example.com/job"),
        location=kwargs.get("location", "Remote"),
        board=kwargs.get("board", "linkedin"),
    )


class TestSeniorFiltersEntryLevel:
    """Senior candidates should not see entry-level jobs."""

    @pytest.mark.parametrize("title", [
        "Full-Stack Software Engineer (New Grad) – Remote",
        "Software Engineer - New Graduate Program",
        "Entry Level Backend Developer",
        "Entry-Level Data Engineer",
        "Summer Intern - Engineering",
        "Software Engineering Internship 2026",
    ])
    def test_filters_entry_level_titles(self, title):
        jobs = [_make_job(title), _make_job("Senior Backend Engineer")]
        result = filter_by_experience_level(jobs, "senior")
        assert len(result) == 1
        assert result[0].title == "Senior Backend Engineer"

    def test_executive_also_filters(self):
        jobs = [_make_job("New Grad SWE"), _make_job("VP Engineering")]
        result = filter_by_experience_level(jobs, "executive")
        assert len(result) == 1
        assert result[0].title == "VP Engineering"

    def test_keeps_senior_and_mid_titles(self):
        jobs = [
            _make_job("Senior Software Engineer"),
            _make_job("Staff Backend Engineer"),
            _make_job("Full-Stack Developer"),
            _make_job("Principal Engineer"),
        ]
        result = filter_by_experience_level(jobs, "senior")
        assert len(result) == 4


class TestNonSeniorKeepsAll:
    """Mid-level and entry-level candidates should see all jobs."""

    @pytest.mark.parametrize("level", ["mid", "entry", None, ""])
    def test_no_filtering(self, level):
        jobs = [
            _make_job("New Grad SWE"),
            _make_job("Senior Backend Engineer"),
            _make_job("Internship Program"),
        ]
        result = filter_by_experience_level(jobs, level)
        assert len(result) == 3


class TestEdgeCases:
    """Edge cases for the filter."""

    def test_empty_job_list(self):
        assert filter_by_experience_level([], "senior") == []

    def test_intern_without_trailing_space(self):
        """'intern' without space should NOT match 'internal' or 'international'."""
        jobs = [
            _make_job("Internal Tools Engineer"),
            _make_job("International Sales Lead"),
            _make_job("Software Intern - Summer 2026"),
        ]
        result = filter_by_experience_level(jobs, "senior")
        # "Internal" and "International" should survive; "Intern " (with space) matches "Software Intern "
        assert len(result) == 2
        titles = {j.title for j in result}
        assert "Internal Tools Engineer" in titles
        assert "International Sales Lead" in titles

    def test_case_insensitive(self):
        jobs = [_make_job("NEW GRAD Software Engineer")]
        result = filter_by_experience_level(jobs, "senior")
        assert len(result) == 0
