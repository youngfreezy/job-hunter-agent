"""Indeed-only searches must use the user's shared browser authentication.

No network, LLM, Browserbase API, or database calls are made by these tests.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.orchestrator.agents.discovery import run_discovery_agent
from backend.shared.config import settings
from backend.shared.models.schemas import JobBoard, JobListing, SearchConfig


def _listing() -> JobListing:
    return JobListing(
        id="indeed-job-1",
        title="Solutions Engineer",
        company="Example Company",
        location="Remote",
        url="https://www.indeed.com/viewjob?jk=example1",
        board=JobBoard.INDEED,
    )


@pytest.fixture
def offline_discovery(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_MODE", "browserbase")
    monkeypatch.setattr(
        "backend.shared.application_store.get_previously_applied_urls", lambda _: set()
    )
    monkeypatch.setattr(
        "backend.shared.application_store.get_rate_limited_companies", lambda _: set()
    )
    monkeypatch.setattr(
        "backend.shared.billing_store.get_blocked_companies", lambda _: set()
    )
    monkeypatch.setattr(
        "backend.moltbook.strategies.get_strategy_manager",
        lambda: SimpleNamespace(
            get_state=lambda: SimpleNamespace(board_priorities={}, human_review_needed=False)
        ),
    )
    mcp = AsyncMock(return_value=[])
    monkeypatch.setattr("backend.browser.tools.mcp_discovery.discover_all_boards", mcp)
    helper_module = ModuleType("backend.browser.tools.indeed_discovery")
    helper_module.discover_indeed = AsyncMock(return_value=[_listing()])
    monkeypatch.setitem(sys.modules, helper_module.__name__, helper_module)
    return helper_module.discover_indeed, mcp


@pytest.mark.asyncio
async def test_indeed_selection_routes_discovery_to_authenticated_browser(offline_discovery):
    indeed, mcp = offline_discovery
    search = SearchConfig(keywords=["solutions engineer"], locations=["Remote"])

    result = await run_discovery_agent({
        "session_id": "ui-session",
        "user_id": "signed-in-user",
        "search_config": search,
        "session_config": {"job_boards": ["indeed"], "max_jobs": 3},
    })

    assert [job.id for job in result["discovered_jobs"]] == ["indeed-job-1"]
    assert result["errors"] == []
    mcp.assert_not_awaited()
    indeed.assert_awaited_once_with(
        search_config=search,
        session_id="ui-session",
        user_id="signed-in-user",
        max_results=3,
        excluded_urls=set(), excluded_companies=set(), excluded_job_keys=set(),
    )


@pytest.mark.asyncio
async def test_indeed_browser_failure_never_falls_back_to_other_boards(offline_discovery):
    indeed, mcp = offline_discovery
    indeed.side_effect = RuntimeError("Indeed browser unavailable")

    result = await run_discovery_agent({
        "session_id": "ui-session",
        "user_id": "signed-in-user",
        "keywords": ["solutions engineer"],
        "session_config": {"job_boards": ["indeed"], "max_jobs": 3},
    })

    assert result["discovered_jobs"] == []
    assert result["errors"], "Browser failure must be visible, not a successful empty ATS search"
    indeed.assert_awaited_once()
    mcp.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("scrape_fails", [False, True], ids=["success", "failure"])
async def test_indeed_scraper_uses_user_context_and_always_releases_session(monkeypatch, scrape_fails):
    # Import inside the test so missing functionality is a focused failure,
    # without preventing the discovery-routing regression from running.
    module = importlib.import_module("backend.browser.tools.indeed_discovery")
    monkeypatch.setattr(settings, "BROWSER_MODE", "browserbase")
    authenticated_context = object()
    manager = MagicMock()
    manager.start_for_task = AsyncMock()
    manager.new_context = AsyncMock(return_value=("shared-context", authenticated_context))
    manager.stop = AsyncMock()
    monkeypatch.setattr(module, "BrowserManager", lambda: manager)
    scraper = AsyncMock(return_value=[_listing()])
    if scrape_fails:
        scraper.side_effect = RuntimeError("scrape failed")
    monkeypatch.setattr(module, "scrape_indeed", scraper)
    search = SearchConfig(keywords=["solutions engineer"], locations=["Remote"])

    if scrape_fails:
        with pytest.raises(RuntimeError, match="scrape failed"):
            await module.discover_indeed(
                search_config=search, session_id="ui-session",
                user_id="signed-in-user", max_results=3,
            )
    else:
        jobs = await module.discover_indeed(
            search_config=search, session_id="ui-session",
            user_id="signed-in-user", max_results=3,
        )
        assert [job.id for job in jobs] == ["indeed-job-1"]

    manager.start_for_task.assert_awaited_once()
    startup = manager.start_for_task.await_args.kwargs
    assert startup["board"] == JobBoard.INDEED
    assert startup["user_id"] == "signed-in-user"
    manager.new_context.assert_awaited_once()
    scraper.assert_awaited_once_with(
        authenticated_context, search, max_results=3,
        excluded_urls=None, excluded_companies=None, excluded_job_keys=None,
    )
    manager.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_indeed_receives_application_and_backfill_exclusions(offline_discovery, monkeypatch):
    indeed, _ = offline_discovery
    prior = _listing()
    monkeypatch.setattr('backend.shared.application_store.get_previously_applied_urls', lambda _: {prior.url})
    monkeypatch.setattr('backend.shared.billing_store.get_blocked_companies', lambda _: {'blocked company'})
    await run_discovery_agent({
        'session_id': 'session', 'user_id': 'user',
        'keywords': ['Engineer'], 'backfill_rounds': 1,
        'discovered_jobs': [prior], 'session_config': {'job_boards': ['indeed'], 'max_jobs': 1},
    })
    kwargs = indeed.await_args.kwargs
    assert kwargs['excluded_urls'] == {prior.url}
    assert kwargs['excluded_companies'] == {'blocked company'}
    assert kwargs['excluded_job_keys'] == {'solutions engineer|example company'}


@pytest.mark.asyncio
async def test_scraper_counts_only_new_eligible_jobs_and_reaches_next_page(monkeypatch):
    from backend.browser.tools.job_boards import indeed as scraper
    prior = _listing()
    blocked = prior.model_copy(update={'id': 'blocked', 'url': 'https://www.indeed.com/viewjob?jk=blocked', 'company': ' BLOCKED '})
    previous_round = prior.model_copy(update={'id': 'seen', 'url': 'https://www.indeed.com/viewjob?jk=seen', 'title': 'Known Engineer', 'company': 'Known'})
    new = prior.model_copy(update={'id': 'new', 'url': 'https://www.indeed.com/viewjob?jk=new', 'company': 'New'})
    page = SimpleNamespace(
        goto=AsyncMock(), wait_for_timeout=AsyncMock(), wait_for_selector=AsyncMock(),
        query_selector_all=AsyncMock(side_effect=[[prior, blocked, previous_round], [new]]), close=AsyncMock(),
    )
    context = SimpleNamespace(pages=[page], new_page=AsyncMock(return_value=page))
    monkeypatch.setattr(scraper, 'apply_stealth', AsyncMock())
    monkeypatch.setattr(scraper, '_is_blocked', AsyncMock(return_value=False))
    monkeypatch.setattr(scraper, '_parse_indeed_card', AsyncMock(side_effect=lambda card, _: card))
    result = await scraper.scrape_indeed(
        context, SearchConfig(keywords=['Engineer'], locations=[]), max_results=1,
        excluded_urls={prior.url}, excluded_companies={'blocked'},
        excluded_job_keys={'known engineer|known'},
    )
    context.new_page.assert_not_awaited()  # Live View must stay on the working tab.
    assert [job.id for job in result] == ['new']
    assert len(page.goto.await_args_list) == 2
    assert 'start=10' in page.goto.await_args_list[1].args[0]
