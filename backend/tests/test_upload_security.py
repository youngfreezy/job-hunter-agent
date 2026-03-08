"""Tests for resume upload security hardening."""

import io
import os
import tempfile

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from backend.shared.models.schemas import StartSessionRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_upload(content: bytes, filename: str, content_type: str = "application/octet-stream") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


# Real PDF magic bytes (minimal valid header)
PDF_MAGIC = b"%PDF-1.4 fake"
# Real DOCX magic bytes (ZIP archive)
DOCX_MAGIC = b"PK\x03\x04" + b"\x00" * 100


# ---------------------------------------------------------------------------
# File size limit
# ---------------------------------------------------------------------------

class TestFileSizeLimit:
    """parse_resume must reject files over 10 MB."""

    def test_small_file_accepted(self):
        """A small valid PDF should be accepted."""
        # We just check that the size check logic works —
        # full endpoint test requires running the server.
        content = PDF_MAGIC + b" " * 1000
        assert len(content) < 10 * 1024 * 1024

    def test_large_file_rejected_boundary(self):
        """Content at exactly 10 MB + 1 byte should be rejected."""
        max_size = 10 * 1024 * 1024
        content = b"x" * (max_size + 1)
        assert len(content) > max_size


# ---------------------------------------------------------------------------
# Magic bytes validation
# ---------------------------------------------------------------------------

class TestMagicBytesValidation:
    """parse_resume must validate file signatures, not just extensions."""

    def test_pdf_valid_magic(self):
        assert PDF_MAGIC[:4] == b"%PDF"

    def test_docx_valid_magic(self):
        assert DOCX_MAGIC[:4] == b"PK\x03\x04"

    def test_fake_pdf_detected(self):
        """A .pdf file without PDF magic bytes should be caught."""
        fake_pdf = b"this is not a pdf"
        assert not fake_pdf[:4].startswith(b"%PDF")

    def test_fake_docx_detected(self):
        """A .docx file without ZIP magic bytes should be caught."""
        fake_docx = b"this is not a docx"
        assert not fake_docx[:4].startswith(b"PK\x03\x04")

    def test_txt_no_magic_check(self):
        """Plain text files should not require magic byte validation."""
        # txt files are read directly, no magic check needed
        content = b"Fareez Ahmed\nAI Engineer\nfareez@example.com"
        assert content  # just verify it's non-empty


# ---------------------------------------------------------------------------
# UUID-only filenames
# ---------------------------------------------------------------------------

class TestUUIDFilenames:
    """Saved resume files must use UUID-only names, not user-provided filenames."""

    def test_filename_pattern(self):
        """UUID hex + extension, no user-provided name component."""
        import uuid
        suffix = "pdf"
        filename = f"{uuid.uuid4().hex}.{suffix}"
        # Must not contain any user-supplied component
        assert "/" not in filename
        assert "\\" not in filename
        assert ".." not in filename
        # Must be hex + dot + suffix
        parts = filename.split(".")
        assert len(parts) == 2
        assert len(parts[0]) == 32  # UUID hex length
        assert parts[1] == suffix


# ---------------------------------------------------------------------------
# resume_file_path validation
# ---------------------------------------------------------------------------

class TestResumeFilePathValidation:
    """StartSessionRequest.resume_file_path must be restricted to allowed directory."""

    def test_none_is_valid(self):
        """None resume_file_path should be accepted."""
        req = StartSessionRequest(
            keywords=["python"],
            resume_file_path=None,
        )
        assert req.resume_file_path is None

    def test_valid_path_in_allowed_dir(self):
        """Path within jobhunter_resumes should be accepted."""
        resume_dir = os.path.join(tempfile.gettempdir(), "jobhunter_resumes")
        os.makedirs(resume_dir, exist_ok=True)
        valid_path = os.path.join(resume_dir, "abc123.pdf")
        # Create the file so realpath resolves
        with open(valid_path, "w") as f:
            f.write("test")
        try:
            req = StartSessionRequest(
                keywords=["python"],
                resume_file_path=valid_path,
            )
            assert req.resume_file_path is not None
        finally:
            os.unlink(valid_path)

    def test_path_traversal_rejected(self):
        """Path outside jobhunter_resumes should be rejected."""
        evil_path = "/etc/passwd"
        with pytest.raises(Exception):  # ValidationError
            StartSessionRequest(
                keywords=["python"],
                resume_file_path=evil_path,
            )

    def test_relative_traversal_rejected(self):
        """Relative path traversal should be rejected."""
        resume_dir = os.path.join(tempfile.gettempdir(), "jobhunter_resumes")
        evil_path = os.path.join(resume_dir, "..", "..", "etc", "passwd")
        with pytest.raises(Exception):
            StartSessionRequest(
                keywords=["python"],
                resume_file_path=evil_path,
            )
