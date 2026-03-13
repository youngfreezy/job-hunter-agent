# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Tests for Pydantic model input validation — verify bad data is rejected."""

import tempfile
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.shared.models.schemas import (
    SessionConfig,
    StartSessionRequest,
)


class TestSessionConfig:
    """SessionConfig should enforce bounds on numeric fields."""

    def test_max_jobs_below_min(self):
        with pytest.raises(ValidationError):
            SessionConfig(max_jobs=0)

    def test_max_jobs_above_max(self):
        with pytest.raises(ValidationError):
            SessionConfig(max_jobs=11)

    def test_max_jobs_valid(self):
        c = SessionConfig(max_jobs=10)
        assert c.max_jobs == 10

    def test_defaults(self):
        c = SessionConfig()
        assert c.max_jobs == 5
        assert c.generate_cover_letters is True


class TestStartSessionRequest:
    """StartSessionRequest validates keywords and resume_file_path."""

    def test_valid_request(self):
        r = StartSessionRequest(keywords=["python"])
        assert r.keywords == ["python"]
        assert r.resume_file_path is None

    def test_resume_path_traversal_blocked(self):
        with pytest.raises(ValidationError, match="Invalid resume file path"):
            StartSessionRequest(
                keywords=["python"],
                resume_file_path="/etc/passwd",
            )

    def test_resume_path_relative_traversal_blocked(self):
        resume_dir = os.path.join(tempfile.gettempdir(), "jobhunter_resumes")
        with pytest.raises(ValidationError, match="Invalid resume file path"):
            StartSessionRequest(
                keywords=["python"],
                resume_file_path=os.path.join(resume_dir, "..", "secret.txt"),
            )

    def test_resume_path_valid(self):
        resume_dir = Path(tempfile.gettempdir(), "jobhunter_resumes")
        resume_dir.mkdir(exist_ok=True)
        test_file = resume_dir / "test_resume.pdf"
        test_file.touch()
        try:
            r = StartSessionRequest(
                keywords=["python"],
                resume_file_path=str(test_file),
            )
            assert "jobhunter_resumes" in r.resume_file_path
        finally:
            test_file.unlink(missing_ok=True)

    def test_empty_keywords_accepted(self):
        # Empty list is technically valid — the pipeline handles it
        r = StartSessionRequest(keywords=[])
        assert r.keywords == []
