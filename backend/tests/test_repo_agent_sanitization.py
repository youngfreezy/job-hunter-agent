"""Moltbook URLs are untrusted data; filters and logs must preserve that boundary."""

import logging

import pytest

from backend.moltbook.sanitize import sanitize


@pytest.mark.parametrize("url", [
    "https://evil.example/?indeed.com",
    "https://notindeed.com/jobs",
    "https://indeed.com.evil.example/jobs",
    "https://indeed.com@evil.example/jobs",
    "https://user:secret@www.indeed.com/jobs",
    "https://www.indeed.com:bad/jobs",
    "https://evil.example/" + "a-" * 120 + "tail-secret",
])
def test_sanitization_rejects_entire_untrusted_url(url):
    assert sanitize(f"Look here {url}", strip_pii=False) == "Look here"


@pytest.mark.parametrize("url", [
    "https://www.indeed.com/viewjob?jk=abc",
    "https://jobs.lever.co/acme/job-id",
    "https://github.com/youngfreezy/job-hunter-agent",
])
def test_sanitization_preserves_allowed_host_and_subdomains(url):
    assert sanitize(url, strip_pii=False) == url


def test_rejected_url_never_enters_sanitizer_logs(caplog, monkeypatch):
    # Earlier migration integration tests configure logging and disable loggers
    # not listed by Alembic. Capture this logger explicitly, independent of order.
    logger = logging.getLogger("backend.moltbook.sanitize")
    monkeypatch.setattr(logger, "disabled", False)
    caplog.set_level(logging.WARNING, logger=logger.name)
    assert sanitize("Look here https://evil.example/?token=private-short") == "Look here"
    assert "private-short" not in caplog.text
    assert "evil.example" not in caplog.text
    assert "url" in caplog.text
