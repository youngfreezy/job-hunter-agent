"""Indeed Apply applier: routing, loud selector failures, logged-in gating."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.browser import browserbase_client as bbc
from backend.browser.tools.appliers import dispatcher, indeed as indeed_mod
from backend.browser.tools.appliers.indeed import IndeedApplier
from backend.browser.tools.ats_detector import detect_ats_from_url
from backend.orchestrator.agents import application as app_node
from backend.shared.config import settings
from backend.shared.models.schemas import (
    ApplicationErrorCategory,
    ApplicationStatus,
    ATSType,
    JobBoard,
    JobListing,
)


def _job(url: str = "https://www.indeed.com/viewjob?jk=abc123") -> JobListing:
    return JobListing(
        id="indeed-1",
        title="Senior Engineer",
        company="Acme",
        location="Austin, TX",
        url=url,
        board=JobBoard.INDEED,
        ats_type=ATSType.UNKNOWN,
        is_easy_apply=True,
        discovered_at=datetime.utcnow(),
    )


@pytest.fixture(autouse=True)
def _no_selector_db(monkeypatch):
    """_click_selector consults the selector-ranking DB; keep tests in-process."""
    monkeypatch.setattr("backend.browser.tools.appliers.base.get_top_selectors", lambda *a, **k: [])
    monkeypatch.setattr("backend.browser.tools.appliers.base.record_success", lambda *a, **k: None)
    monkeypatch.setattr("backend.browser.tools.appliers.base.record_failure", lambda *a, **k: None)
    monkeypatch.setattr("backend.browser.tools.appliers.base.emit_agent_event", AsyncMock())


# ---------------------------------------------------------------------------
# detection + routing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url", [
    "https://www.indeed.com/viewjob?jk=abc123",
    "https://indeed.com/viewjob?jk=abc123",
    "https://uk.indeed.com/viewjob?jk=abc123",
    "https://smartapply.indeed.com/beta/indeedapply/form/contact-info",
])
def test_detect_ats_recognises_indeed(url):
    assert detect_ats_from_url(url) == ATSType.INDEED


def test_detect_ats_does_not_match_lookalike_hosts():
    assert detect_ats_from_url("https://notindeed.com/jobs/1") == ATSType.UNKNOWN
    assert detect_ats_from_url("https://boards.greenhouse.io/acme/jobs/1") == ATSType.GREENHOUSE


@pytest.mark.asyncio
async def test_dispatcher_routes_indeed_urls_to_indeed_applier(monkeypatch):
    run = AsyncMock(return_value=MagicMock(status=ApplicationStatus.SUBMITTED))
    monkeypatch.setattr(IndeedApplier, "run", run)
    page = MagicMock(url="https://www.indeed.com/viewjob?jk=abc123")

    await dispatcher.apply_with_playwright(
        job=_job(), user_profile={}, resume_text="", cover_letter="",
        resume_file_path=None, session_id="s1", page=page,
    )

    run.assert_awaited_once()
    assert dispatcher._APPLIER_MAP[ATSType.INDEED] is IndeedApplier


# ---------------------------------------------------------------------------
# applier behaviour
# ---------------------------------------------------------------------------


def _page(url: str = "https://www.indeed.com/viewjob?jk=abc123"):
    page = MagicMock()
    page.url = url
    page.query_selector = AsyncMock(return_value=None)
    page.wait_for_selector = AsyncMock(side_effect=TimeoutError("no element"))
    page.evaluate = AsyncMock(return_value=[])
    page.wait_for_load_state = AsyncMock()
    return page


@pytest.mark.asyncio
async def test_apply_button_miss_fails_loudly_naming_unverified_selectors(monkeypatch):
    monkeypatch.setattr(indeed_mod, "SELECTORS_VERIFIED", False)
    applier = IndeedApplier(_page(), "s1")
    monkeypatch.setattr(applier, "_random_delay", AsyncMock())

    result = await applier.run(job=_job(), user_profile={}, resume_text="", cover_letter="")

    assert result.status == ApplicationStatus.FAILED
    assert result.failure_step == "page_load"
    assert result.error_category == ApplicationErrorCategory.FORM_NAVIGATION
    assert result.ats_type == "indeed"
    assert "apply_button" in result.error_message
    assert "UNVERIFIED" in result.error_message
    assert "#indeedApplyButton" in result.error_message
    assert "TODO(unverified-selectors)" in result.error_message


@pytest.mark.asyncio
async def test_signed_out_context_fails_as_auth_required(monkeypatch):
    applier = IndeedApplier(_page("https://secure.indeed.com/account/login?hl=en&continue=x"), "s1")

    result = await applier.run(job=_job(), user_profile={}, resume_text="", cover_letter="")

    assert result.status == ApplicationStatus.FAILED
    assert result.error_category == ApplicationErrorCategory.AUTH_REQUIRED
    assert "not logged in" in result.error_message


@pytest.mark.asyncio
async def test_wizard_continues_then_submits(monkeypatch):
    applier = IndeedApplier(_page(), "s1")
    clicks: list[str] = []
    outcomes = {"apply_button": [True], "next_button": [True, True, False], "submit_button": [True]}

    async def fake_click(hardcoded, step_type, timeout=5000):
        clicks.append(step_type)
        return outcomes[step_type].pop(0)

    fill = AsyncMock(return_value={"filled": 3, "skipped": 0, "errors": []})
    submitted = applier._make_result("indeed-1", ApplicationStatus.SUBMITTED)
    monkeypatch.setattr(applier, "_click_selector", fake_click)
    monkeypatch.setattr(applier, "_fill_current_form", fill)
    monkeypatch.setattr(applier, "_random_delay", AsyncMock())
    monkeypatch.setattr(applier, "_wait_for_navigation", AsyncMock())
    monkeypatch.setattr(applier, "_capture_screenshot", AsyncMock())
    monkeypatch.setattr(applier, "_post_submit_check", AsyncMock(return_value=submitted))

    result = await applier.run(job=_job(), user_profile={"name": "Ada"}, resume_text="r", cover_letter="c")

    assert result.status == ApplicationStatus.SUBMITTED
    assert result.ats_type == "indeed"
    assert clicks == ["apply_button", "next_button", "next_button", "next_button", "submit_button"]
    assert fill.await_count == 3  # one form fill per wizard step


@pytest.mark.asyncio
async def test_missing_submit_control_fails_loudly(monkeypatch):
    applier = IndeedApplier(_page(), "s1")

    async def fake_click(hardcoded, step_type, timeout=5000):
        return step_type == "apply_button"

    monkeypatch.setattr(applier, "_click_selector", fake_click)
    monkeypatch.setattr(applier, "_fill_current_form", AsyncMock(return_value={"filled": 0, "skipped": 0, "errors": []}))
    monkeypatch.setattr(applier, "_random_delay", AsyncMock())
    monkeypatch.setattr(applier, "_wait_for_navigation", AsyncMock())

    result = await applier.run(job=_job(), user_profile={}, resume_text="", cover_letter="")

    assert result.status == ApplicationStatus.FAILED
    assert result.failure_step == "submit"
    assert "Submit your application" in result.error_message
    assert "UNVERIFIED" in result.error_message


@pytest.mark.asyncio
async def test_parked_by_owner_rules_escapes_to_skipped(monkeypatch):
    from backend.shared.application_rules import ApplicationParked

    applier = IndeedApplier(_page(), "s1", application_rules="Park on AI questions")
    monkeypatch.setattr(applier, "_click_selector", AsyncMock(return_value=True))
    monkeypatch.setattr(applier, "_random_delay", AsyncMock())
    monkeypatch.setattr(applier, "_wait_for_navigation", AsyncMock())
    monkeypatch.setattr(
        applier, "_fill_current_form",
        AsyncMock(side_effect=ApplicationParked("Are you using an AI agent to apply?")),
    )

    result = await applier.run(job=_job(), user_profile={}, resume_text="", cover_letter="")

    assert result.status == ApplicationStatus.SKIPPED
    assert result.error_message == "Are you using an AI agent to apply?"


# ---------------------------------------------------------------------------
# application-node gating
# ---------------------------------------------------------------------------


def test_board_login_available_requires_browserbase_mode_and_context(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_MODE", "browserbase")
    monkeypatch.setattr(bbc, "config_for_user", lambda uid: bbc.BrowserbaseConfig(context_ids={"indeed": "ctx-indeed"}))
    assert app_node._board_login_available(JobBoard.INDEED, "user-1") is True
    assert app_node._board_login_available("indeed", "user-1") is True
    assert app_node._board_login_available(JobBoard.GLASSDOOR, "user-1") is False

    monkeypatch.setattr(bbc, "config_for_user", lambda uid: bbc.BrowserbaseConfig(context_ids={"default": "ctx-default"}))
    assert app_node._board_login_available(JobBoard.INDEED, "user-1") is False  # default ctx is not a login

    monkeypatch.setattr(settings, "BROWSER_MODE", "cdp")
    monkeypatch.setattr(bbc, "config_for_user", lambda uid: bbc.BrowserbaseConfig(context_ids={"indeed": "ctx-indeed"}))
    assert app_node._board_login_available(JobBoard.INDEED, "user-1") is False
