"""Browserbase Fetch API discovery verifier: verdicts, request shape, shortlist gating."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.browser import fetch_verifier as fv
from backend.browser.browserbase_client import BrowserbaseConfig, BrowserbaseError
from backend.orchestrator.agents import scoring
from backend.shared.config import settings
from backend.shared.models.schemas import ATSType, JobBoard, JobListing, ScoredJob


@pytest.fixture(autouse=True)
def _bb_settings(monkeypatch):
    monkeypatch.setattr(settings, "BROWSERBASE_CONTEXT_USER_ID", "verifier-test-owner")
    monkeypatch.setattr("backend.shared.browserbase_store.get_browserbase_settings", lambda _: None)
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", "bb_live_test")
    monkeypatch.setattr(settings, "BROWSERBASE_PROJECT_ID", "proj-123")
    monkeypatch.setattr(settings, "BROWSERBASE_PROXIES", False)
    monkeypatch.setattr(settings, "BROWSERBASE_VERIFY_LISTINGS", True)
    monkeypatch.setattr("backend.shared.billing_store.get_blocked_companies", lambda _: set())
    monkeypatch.setattr("backend.shared.application_rules.load_application_rules", lambda _: "")


# A documented 200 response from POST /v1/fetch.
def _fetch_payload(content, status_code=200, content_type="text/html; charset=utf-8"):
    return {
        "id": "fetch_abc",
        "statusCode": status_code,
        "headers": {"content-type": content_type},
        "content": content,
        "contentType": content_type,
        "encoding": "utf-8",
    }


# Long enough to count as a real page rather than a client-rendered shell.
_LONG_NO_APPLY = "# Engineer\n\n" + "Great role working on search infrastructure. Email us your CV. " * 8


def _job(job_id: str, url: str | None = None) -> JobListing:
    return JobListing(
        id=job_id,
        title=f"Engineer {job_id}",
        company=f"Co {job_id}",
        location="Remote",
        url=url or f"https://boards.greenhouse.io/co/jobs/{job_id}",
        board=JobBoard.GOOGLE_JOBS,
        ats_type=ATSType.GREENHOUSE,
        discovered_at=datetime.utcnow(),
    )


def _scored(job_id: str, score: int) -> ScoredJob:
    return ScoredJob(job=_job(job_id), score=score)


class _FakeResponse:
    def __init__(self, status_code, payload, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else str(payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _client(response):
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=response)
    return client


# ---------------------------------------------------------------------------
# judge_listing
# ---------------------------------------------------------------------------


def test_judge_open_listing_with_apply_link():
    md = "# Senior Engineer\n\nWe build things.\n\n[Apply for this job](https://boards.greenhouse.io/co/jobs/1#app)\n"
    ok, note = fv.judge_listing(fv.FetchResult(markdown=md, status_code=200))
    assert ok is True
    assert note.startswith("open: apply link")


def test_judge_open_listing_with_bare_apply_button_text():
    md = "Senior Engineer\n\nLocation: Remote\n\nApply now\n\nAbout us..."
    ok, note = fv.judge_listing(fv.FetchResult(markdown=md))
    assert ok is True
    assert "Apply now" in note


@pytest.mark.parametrize("phrase", [
    "This job is no longer available.",
    "Sorry, we are no longer accepting applications for this position.",
    "This position has been filled",
])
def test_judge_closed_copy_wins_over_apply_control(phrase):
    md = f"# Engineer\n\n{phrase}\n\n[Apply now](https://x)\n"
    ok, note = fv.judge_listing(fv.FetchResult(markdown=md, status_code=200))
    assert ok is False
    assert note.startswith("closed: page says")


@pytest.mark.parametrize("code", [404, 410])
def test_judge_gone_is_closed(code):
    ok, note = fv.judge_listing(fv.FetchResult(markdown="[Apply](x)", status_code=code))
    assert (ok, note) == (False, f"closed: page returned HTTP {code}")


@pytest.mark.parametrize("code", [401, 403, 429, 500, 503])
def test_judge_other_http_errors_are_unverified_not_closed(code):
    """A bot block or outage says nothing about the requisition."""
    ok, note = fv.judge_listing(fv.FetchResult(markdown="", status_code=code))
    assert ok is False
    assert note == f"unverified: page returned HTTP {code}"
    job = _job("x")
    job.verified_open, job.verify_note = ok, note
    assert fv._is_positively_closed(job) is False


def test_judge_no_apply_control_on_a_full_page_is_not_open():
    assert len(_LONG_NO_APPLY) >= fv.MIN_TEXT_CHARS
    ok, note = fv.judge_listing(fv.FetchResult(markdown=_LONG_NO_APPLY, status_code=200))
    assert ok is False
    assert note == "no Apply control found in page text"


def test_judge_thin_page_without_apply_is_unverified():
    """Fetch runs no JavaScript: a short shell is not evidence the job is apply-less."""
    md = "# Engineer\n\nGreat role. Email us your CV.\n"
    ok, note = fv.judge_listing(fv.FetchResult(markdown=md, status_code=200))
    assert ok is False
    assert note.startswith("unverified: page too thin to judge")
    job = _job("x")
    job.verified_open, job.verify_note = ok, note
    assert fv._is_positively_closed(job) is False


def test_judge_closed_copy_on_thin_page_still_closes():
    ok, note = fv.judge_listing(fv.FetchResult(markdown="This job is no longer available.", status_code=200))
    assert (ok, note) == (False, "closed: page says 'no longer available'")


def test_judge_does_not_match_apply_inside_prose():
    md = "# Engineer\n\nYou will apply machine learning to search problems.\n"
    ok, _ = fv.judge_listing(fv.FetchResult(markdown=md))
    assert ok is False


def test_judge_empty_page_is_unverified():
    ok, note = fv.judge_listing(fv.FetchResult(markdown="  \n"))
    assert ok is False
    assert note.startswith("unverified: page has no text")


# ---------------------------------------------------------------------------
# _html_to_markdown (raw fallback)
# ---------------------------------------------------------------------------


def test_html_to_markdown_keeps_links_buttons_and_line_structure():
    raw = (
        "<html><head><title>T</title><style>a{}</style></head><body>"
        "<script>var x = 1;</script>"
        "<h1>Senior   Engineer</h1><p>Remote &amp; hybrid.</p>"
        '<a class="btn" href="https://x/apply">Apply <span>now</span></a>'
        "<div><button type='submit'>Submit application</button></div>"
        '<input type="submit" value="Apply for this job">'
        "</body></html>"
    )
    md = fv._html_to_markdown(raw)
    assert "var x" not in md and "a{}" not in md
    assert "Senior Engineer" in md and "Remote & hybrid." in md
    assert "[Apply now](https://x/apply)" in md
    assert "\nSubmit application\n" in f"\n{md}\n"
    assert "\nApply for this job\n" in f"\n{md}\n"
    ok, note = fv.judge_listing(fv.FetchResult(markdown=md, status_code=200, source_format="raw"))
    assert ok is True and note.startswith("open: apply link")


# ---------------------------------------------------------------------------
# fetch_markdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_markdown_posts_the_documented_request_and_reads_content():
    client = _client(_FakeResponse(200, _fetch_payload("# Hi\n[Apply](x)")))
    with patch.object(fv.httpx, "AsyncClient", return_value=client):
        result = await fv.fetch_markdown("https://example.com/job/1")

    args, kwargs = client.post.await_args
    assert args[0] == "https://api.browserbase.com/v1/fetch"
    assert kwargs["headers"]["X-BB-API-Key"] == "bb_live_test"
    # Exactly the fields the reference documents; job URLs redirect, so follow them.
    assert kwargs["json"] == {"url": "https://example.com/job/1", "format": "markdown", "allowRedirects": True}
    assert result.markdown.startswith("# Hi")
    assert result.status_code == 200
    assert result.content_type.startswith("text/html")
    assert result.source_format == "markdown"


@pytest.mark.asyncio
async def test_fetch_markdown_routes_through_proxies_when_configured():
    client = _client(_FakeResponse(200, _fetch_payload("[Apply](x)")))
    cfg = BrowserbaseConfig(api_key="bb_user", project_id="p", proxies=True)
    with patch.object(fv.httpx, "AsyncClient", return_value=client):
        await fv.fetch_markdown("https://example.com", cfg)
    _, kwargs = client.post.await_args
    assert kwargs["headers"]["X-BB-API-Key"] == "bb_user"
    assert kwargs["json"]["proxies"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [402, 403])
async def test_fetch_markdown_falls_back_to_raw_html_when_markdown_is_unavailable(code):
    html = "<html><body><h1>Engineer</h1><p>Text</p><a href='https://x/a'>Apply now</a></body></html>"
    client = _client(None)
    client.post = AsyncMock(side_effect=[
        _FakeResponse(code, {"statusCode": code, "error": "Forbidden", "message": "format not enabled"}),
        _FakeResponse(200, _fetch_payload(html)),
    ])
    with patch.object(fv.httpx, "AsyncClient", return_value=client):
        result = await fv.fetch_markdown("https://example.com/job/1")

    first, second = client.post.await_args_list
    assert first.kwargs["json"]["format"] == "markdown"
    assert second.kwargs["json"]["format"] == "raw"
    assert second.kwargs["json"]["allowRedirects"] is True
    assert result.source_format == "raw"
    assert "[Apply now](https://x/a)" in result.markdown
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_fetch_markdown_raw_fallback_rejects_non_text_content():
    client = _client(None)
    client.post = AsyncMock(side_effect=[
        _FakeResponse(403, {"statusCode": 403, "error": "Forbidden", "message": "x"}),
        _FakeResponse(200, _fetch_payload("%PDF-1.4", content_type="application/pdf")),
    ])
    with patch.object(fv.httpx, "AsyncClient", return_value=client):
        with pytest.raises(BrowserbaseError, match="non-text content"):
            await fv.fetch_markdown("https://example.com/cv.pdf")


@pytest.mark.asyncio
async def test_fetch_markdown_reports_upstream_status_code():
    client = _client(_FakeResponse(200, _fetch_payload("Forbidden", status_code=403)))
    with patch.object(fv.httpx, "AsyncClient", return_value=client):
        result = await fv.fetch_markdown("https://example.com")
    assert result.status_code == 403
    assert fv.judge_listing(result) == (False, "unverified: page returned HTTP 403")


@pytest.mark.asyncio
async def test_fetch_markdown_raises_on_http_error():
    client = _client(_FakeResponse(401, {"error": "Unauthorized"}))
    with patch.object(fv.httpx, "AsyncClient", return_value=client):
        with pytest.raises(BrowserbaseError, match="fetch failed: 401"):
            await fv.fetch_markdown("https://example.com")


@pytest.mark.asyncio
async def test_fetch_markdown_raises_when_response_has_no_content():
    client = _client(_FakeResponse(200, {"id": "abc", "statusCode": 200}))
    with patch.object(fv.httpx, "AsyncClient", return_value=client):
        with pytest.raises(BrowserbaseError, match="no string content"):
            await fv.fetch_markdown("https://example.com")


@pytest.mark.asyncio
async def test_fetch_markdown_raises_when_response_is_not_json():
    client = _client(_FakeResponse(200, ValueError("bad json"), text="<html>oops</html>"))
    with patch.object(fv.httpx, "AsyncClient", return_value=client):
        with pytest.raises(BrowserbaseError, match="not JSON"):
            await fv.fetch_markdown("https://example.com")


@pytest.mark.asyncio
async def test_fetch_markdown_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", None)
    with pytest.raises(BrowserbaseError):
        await fv.fetch_markdown("https://example.com")


# ---------------------------------------------------------------------------
# verify_shortlist_candidates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_shortlist_drops_closed_keeps_open_and_errored(monkeypatch):
    pages = {
        "https://boards.greenhouse.io/co/jobs/open": fv.FetchResult("[Apply now](x)", 200),
        "https://boards.greenhouse.io/co/jobs/closed": fv.FetchResult("This job is no longer available", 200),
        "https://boards.greenhouse.io/co/jobs/noapply": fv.FetchResult(_LONG_NO_APPLY, 200),
        "https://boards.greenhouse.io/co/jobs/thin": fv.FetchResult("Loading...", 200),
        "https://boards.greenhouse.io/co/jobs/blocked": fv.FetchResult("", 403),
    }

    async def fake_fetch(url, config=None):
        if url.endswith("/errored"):
            raise BrowserbaseError("fetch failed: 503 upstream")
        return pages[url]

    monkeypatch.setattr(fv, "fetch_markdown", fake_fetch)
    events: list = []

    async def fake_emit(_sid, event, payload):
        events.append((event, payload))

    monkeypatch.setattr(fv, "emit_agent_event", fake_emit)

    jobs = [
        _scored("open", 90), _scored("closed", 85), _scored("errored", 80),
        _scored("noapply", 70), _scored("thin", 60), _scored("blocked", 50),
    ]
    kept = await fv.verify_shortlist_candidates(jobs, session_id="s1", user_id="verifier-test-owner")

    # Only positive findings (closed copy, a full page with no Apply control) drop a job;
    # errors, thin client-rendered shells and bot blocks keep it with the reason recorded.
    assert [sj.job.id for sj in kept] == ["open", "errored", "thin", "blocked"]
    assert jobs[0].job.verified_open is True
    assert jobs[1].job.verify_note.startswith("closed:")
    assert jobs[2].job.verified_open is False
    assert jobs[2].job.verify_note.startswith("verifier error: fetch failed: 503")
    assert jobs[3].job.verify_note == "no Apply control found in page text"
    assert jobs[4].job.verify_note.startswith("unverified: page too thin")
    assert jobs[5].job.verify_note == "unverified: page returned HTTP 403"

    summary = next(p for ev, p in events if ev == "listing_verification")
    assert summary["checked"] == 6
    assert summary["verified_open"] == 1
    assert summary["removed"] == 2
    assert {r["job_id"] for r in summary["removed_jobs"]} == {"closed", "noapply"}


@pytest.mark.asyncio
async def test_verify_shortlist_respects_limit(monkeypatch):
    seen: list[str] = []

    async def fake_fetch(url, config=None):
        seen.append(url)
        return fv.FetchResult("[Apply](x)", 200)

    monkeypatch.setattr(fv, "fetch_markdown", fake_fetch)
    monkeypatch.setattr(fv, "emit_agent_event", AsyncMock())

    jobs = [_scored(str(i), 90 - i) for i in range(5)]
    kept = await fv.verify_shortlist_candidates(jobs, session_id="s1", user_id="verifier-test-owner", limit=3)

    assert len(seen) == 3
    assert len(kept) == 5
    assert all(sj.job.verified_open for sj in jobs[:3])
    assert jobs[4].job.verify_note == "not verified: beyond verification budget"


@pytest.mark.asyncio
async def test_verify_shortlist_skips_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "BROWSERBASE_API_KEY", None)
    fetch = AsyncMock()
    monkeypatch.setattr(fv, "fetch_markdown", fetch)

    jobs = [_scored("a", 90)]
    kept = await fv.verify_shortlist_candidates(jobs, session_id="s1", user_id="verifier-test-owner")

    fetch.assert_not_awaited()
    assert kept == jobs
    assert jobs[0].job.verified_open is False
    assert jobs[0].job.verify_note == "verifier skipped: BROWSERBASE_API_KEY not set"


@pytest.mark.asyncio
async def test_verify_shortlist_honours_disable_flag(monkeypatch):
    monkeypatch.setattr(settings, "BROWSERBASE_VERIFY_LISTINGS", False)
    fetch = AsyncMock()
    monkeypatch.setattr(fv, "fetch_markdown", fetch)

    jobs = [_scored("a", 90)]
    await fv.verify_shortlist_candidates(jobs, user_id="verifier-test-owner")

    fetch.assert_not_awaited()
    assert jobs[0].job.verify_note == "verifier disabled (BROWSERBASE_VERIFY_LISTINGS=false)"


@pytest.mark.asyncio
async def test_verify_listing_prefers_external_apply_url(monkeypatch):
    seen: list[str] = []

    async def fake_fetch(url, config=None):
        seen.append(url)
        return fv.FetchResult("[Apply](x)", 200)

    monkeypatch.setattr(fv, "fetch_markdown", fake_fetch)
    job = _job("x", url="https://www.linkedin.com/jobs/view/1")
    job.external_apply_url = "https://jobs.lever.co/co/1"
    await fv.verify_listing(job)
    assert seen == ["https://jobs.lever.co/co/1"]


# ---------------------------------------------------------------------------
# scoring integration
# ---------------------------------------------------------------------------


class _FakeLLM:
    def with_structured_output(self, _schema):
        return self


@pytest.mark.asyncio
async def test_scoring_runs_verifier_before_capping_shortlist(monkeypatch):
    async def fake_invoke(_llm, messages, **_kwargs):
        ids = [l.replace("- ID: ", "").strip() for l in messages[-1].content.splitlines() if l.startswith("- ID: ")]
        return scoring.ScoringBatchResult(scores=[{
            "job_id": jid, "score": 80,
            "score_breakdown": {"keyword_match": 80, "location_match": 100, "salary_match": 50, "experience_match": 80},
            "reasons": ["fit", "fit"],
        } for jid in ids])

    monkeypatch.setattr(scoring, "build_llm", lambda **_: _FakeLLM())
    monkeypatch.setattr(scoring, "invoke_with_retry", fake_invoke)
    monkeypatch.setattr(scoring, "emit_agent_event", AsyncMock())
    monkeypatch.setattr(scoring, "get_active_prompt", lambda _key: None)

    async def fake_fetch(url, config=None):
        if url.endswith("/1"):
            return fv.FetchResult("This job is no longer available", 200)
        return fv.FetchResult("[Apply now](x)", 200)

    monkeypatch.setattr(fv, "fetch_markdown", fake_fetch)
    monkeypatch.setattr(fv, "emit_agent_event", AsyncMock())

    result = await scoring.run_scoring_agent({
        "session_id": "verify-test",
        "user_id": "verifier-test-owner",
        "resume_text": "Python engineer",
        "discovered_jobs": [_job("0"), _job("1"), _job("2")],
        "session_config": {"max_jobs": 2, "scoring_strictness": 0.0},
    })

    scored = result["scored_jobs"]
    assert [sj.job.id for sj in scored] == ["0", "2"]
    assert all(sj.job.verified_open for sj in scored)
    assert all(sj.job.verify_note.startswith("open:") for sj in scored)
