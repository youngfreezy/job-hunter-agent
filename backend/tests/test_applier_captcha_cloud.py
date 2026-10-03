"""CAPTCHA handling after submit: 2captcha when keyed, Browserbase sessions otherwise."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.browser.tools.appliers import base as base_mod
from backend.browser.tools.appliers.base import BaseApplier
from backend.shared.config import settings
from backend.shared.models.schemas import ApplicationStatus, ATSType, JobBoard, JobListing


class _Applier(BaseApplier):
    PLATFORM = "test"

    async def apply(self, job, user_profile, resume_text, cover_letter, resume_file_path=None):  # pragma: no cover
        raise NotImplementedError


def _applier(monkeypatch, *, captcha: bool, confirmations: list[bool], solved: bool = False):
    monkeypatch.setattr(base_mod, "emit_agent_event", AsyncMock())
    monkeypatch.setattr(base_mod.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr("backend.browser.tools.captcha_solver.solve_captcha", AsyncMock(return_value=solved))
    applier = _Applier(page=MagicMock(), session_id="s1")
    applier._detect_verification_prompt = AsyncMock(return_value=False)
    applier._has_recaptcha = AsyncMock(return_value=captcha)
    applier._detect_confirmation = AsyncMock(side_effect=confirmations + [confirmations[-1]] * 20)
    applier._click_selectors = AsyncMock(return_value=True)
    applier._detect_failure = AsyncMock(return_value="captcha" if captcha else None)
    return applier


@pytest.mark.asyncio
async def test_browserbase_mode_waits_for_the_cloud_browser_and_confirms(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_MODE", "browserbase")
    monkeypatch.setattr(settings, "CAPTCHA_API_KEY", None)
    applier = _applier(monkeypatch, captcha=True, confirmations=[False, False, True])

    result = await applier._post_submit_check("job-1", cover_letter="cl")

    assert result.status == ApplicationStatus.SUBMITTED
    assert result.cover_letter_used == "cl"
    base_mod.asyncio.sleep.assert_any_await(base_mod.CLOUD_CAPTCHA_SETTLE_SECONDS)
    applier._click_selectors.assert_not_awaited()  # nothing to re-click, Browserbase handles the widget


@pytest.mark.asyncio
async def test_browserbase_mode_reports_when_the_challenge_is_not_cleared(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_MODE", "browserbase")
    monkeypatch.setattr(settings, "CAPTCHA_API_KEY", None)
    applier = _applier(monkeypatch, captcha=True, confirmations=[False])

    result = await applier._post_submit_check("job-1")

    assert result.status == ApplicationStatus.FAILED
    assert "Browserbase session did not clear it" in (result.error_message or "")
    # Longer confirmation window than the plain 5 polls.
    assert applier._detect_confirmation.await_count == base_mod.CLOUD_CAPTCHA_CONFIRM_ATTEMPTS


@pytest.mark.asyncio
async def test_local_browser_without_solver_still_fails_fast(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_MODE", "cdp")
    monkeypatch.setattr(settings, "CAPTCHA_API_KEY", None)
    applier = _applier(monkeypatch, captcha=True, confirmations=[True])

    result = await applier._post_submit_check("job-1")

    assert result.status == ApplicationStatus.FAILED
    assert (result.error_message or "").startswith("CAPTCHA unsolvable")
    applier._detect_confirmation.assert_not_awaited()


@pytest.mark.asyncio
async def test_solved_captcha_reclicks_submit_in_any_mode(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_MODE", "browserbase")
    applier = _applier(monkeypatch, captcha=True, confirmations=[True], solved=True)

    result = await applier._post_submit_check("job-1")

    assert result.status == ApplicationStatus.SUBMITTED
    applier._click_selectors.assert_awaited_once_with("submit_button")


@pytest.mark.asyncio
async def test_no_captcha_path_is_unchanged(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_MODE", "browserbase")
    applier = _applier(monkeypatch, captcha=False, confirmations=[False, True])

    result = await applier._post_submit_check("job-1")

    assert result.status == ApplicationStatus.SUBMITTED
    assert applier._detect_confirmation.await_count == 2
