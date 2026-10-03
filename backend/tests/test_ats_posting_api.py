"""Posting-API hydration: URL parsing, vendor documents, gone postings, errors."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.browser.tools import ats_posting_api as api
from backend.shared.models.schemas import ATSType, JobBoard, JobListing


def _job(url, location="", **kw):
    return JobListing(id="j1", title=kw.pop("title", "AI Engineer"), company=kw.pop("company", "Acme"),
                      location=location, url=url, board=JobBoard.GOOGLE_JOBS, discovered_at=datetime.utcnow(), **kw)


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=MagicMock(), response=MagicMock(status_code=self.status_code))

    def json(self):
        return self._payload


def _client(*responses):
    client = MagicMock()
    client.get = AsyncMock(side_effect=list(responses))
    return client


@pytest.mark.parametrize("url,expected", [
    ("https://jobs.lever.co/AIFund/01654e18-7b7f-4f0d-84b4-9e090fbc73be", ("lever", "AIFund", "01654e18-7b7f-4f0d-84b4-9e090fbc73be")),
    ("https://jobs.lever.co/neon/f9b925d6-38e1-4b24-9adb-4cbbcca3100f/apply", ("lever", "neon", "f9b925d6-38e1-4b24-9adb-4cbbcca3100f")),
    ("https://job-boards.greenhouse.io/anthropic/jobs/5390799008", ("greenhouse", "anthropic", "5390799008")),
    ("https://boards.greenhouse.io/censys/jobs/8540995002?gh_src=x", ("greenhouse", "censys", "8540995002")),
    ("https://jobs.ashbyhq.com/gamma/6ed26f6b-bb17-41a5-8f63-f1901554cb6b?gh_src=Accel", ("ashby", "gamma", "6ed26f6b-bb17-41a5-8f63-f1901554cb6b")),
    ("https://jobs.ashbyhq.com/workos/5e650527-d8dd-413a-9cfb-d7d68143274b/application", ("ashby", "workos", "5e650527-d8dd-413a-9cfb-d7d68143274b")),
    ("https://www.indeed.com/viewjob?jk=abc", None),
    ("https://hex.tech/careers/x?gh_jid=5808072004", None),
])
def test_parse_posting_ref(url, expected):
    ref = api.parse_posting_ref(url)
    assert (ref and (ref.ats, ref.org, ref.posting_id)) == expected


@pytest.mark.asyncio
async def test_lever_posting_fills_location_pay_and_description():
    job = _job("https://jobs.lever.co/acme/11111111-1111-1111-1111-111111111111")
    client = _client(_Resp(200, {
        "text": "Senior Applied AI Engineer",
        "categories": {"location": "San Francisco, CA", "team": "Engineering", "allLocations": ["San Francisco, CA", "New York, NY"]},
        "workplaceType": "hybrid",
        "salaryRange": {"min": 180000, "max": 240000, "currency": "USD", "interval": "per-year-salary"},
        "descriptionPlain": "Build agents. " * 60,
    }))
    h = await api.hydrate_listing(job, client)
    assert h.found is True and h.source == "lever"
    assert job.location == "San Francisco, CA | New York, NY (hybrid)"
    assert job.is_remote is False
    assert job.salary_range == "USD 180,000 - 240,000 per per year salary"
    assert job.description_snippet.startswith("Build agents.") and len(job.description_snippet) <= 500
    assert client.get.await_args.args[0] == "https://api.lever.co/v0/postings/acme/11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
async def test_lever_remote_posting_sets_remote_flag():
    job = _job("https://jobs.lever.co/acme/11111111-1111-1111-1111-111111111111")
    client = _client(_Resp(200, {"text": "AI Engineer", "categories": {"location": "United States"}, "workplaceType": "remote"}))
    await api.hydrate_listing(job, client)
    assert job.location == "United States (remote)" and job.is_remote is True


@pytest.mark.asyncio
async def test_greenhouse_job_fills_from_location_and_content():
    job = _job("https://job-boards.greenhouse.io/anthropic/jobs/5390799008", company="Unknown")
    client = _client(_Resp(200, {
        "title": "Applied AI Engineer", "company_name": "Anthropic",
        "location": {"name": "San Francisco, CA | New York City, NY"},
        "content": "&lt;p&gt;We are hiring &amp; building.&lt;/p&gt;",
        "metadata": [{"name": "Salary Range", "value": "$300,000 - $405,000 USD"}],
    }))
    h = await api.hydrate_listing(job, client)
    assert h.found is True
    assert job.location == "San Francisco, CA | New York City, NY"
    assert job.company == "Anthropic"
    assert job.description_snippet == "We are hiring & building."
    assert job.salary_range == "$300,000 - $405,000 USD"
    assert client.get.await_args.args[0] == "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs/5390799008"


@pytest.mark.asyncio
async def test_ashby_board_matches_posting_by_id(monkeypatch):
    api._ashby_board_cache.clear()
    job = _job("https://jobs.ashbyhq.com/gamma/6ed26f6b-bb17-41a5-8f63-f1901554cb6b")
    board = {"apiVersion": "1", "jobs": [
        {"id": "other", "title": "x", "location": "Berlin"},
        {"id": "6ED26F6B-BB17-41A5-8F63-F1901554CB6B", "title": "AI Engineer", "location": "San Francisco",
         "isRemote": False, "secondaryLocations": [{"location": "New York"}],
         "compensation": {"compensationTierSummary": "$170K – $230K • Offers Equity"},
         "descriptionPlain": "Ship AI features."},
    ]}
    client = _client(_Resp(200, board))
    h = await api.hydrate_listing(job, client)
    assert h.found is True and h.source == "ashby"
    assert job.location == "San Francisco | New York"
    assert job.salary_range == "$170K – $230K • Offers Equity"
    assert job.description_snippet == "Ship AI features."
    assert "includeCompensation=true" in client.get.await_args.args[0]
    # second posting on the same board reuses the cached document
    job2 = _job("https://jobs.ashbyhq.com/gamma/00000000-0000-0000-0000-000000000000")
    h2 = await api.hydrate_listing(job2, client)
    assert h2.found is False  # board served, posting not listed any more
    assert client.get.await_count == 1


@pytest.mark.asyncio
async def test_gone_postings_are_reported_not_raised():
    job = _job("https://jobs.lever.co/acme/11111111-1111-1111-1111-111111111111", location="Remote")
    h = await api.hydrate_listing(job, _client(_Resp(404)))
    assert h.found is False and job.location == "Remote"


@pytest.mark.asyncio
async def test_vendor_errors_leave_the_listing_unchanged():
    job = _job("https://job-boards.greenhouse.io/acme/jobs/1", location="Unknown")
    h = await api.hydrate_listing(job, _client(_Resp(503)))
    assert h.found is None and job.location == "Unknown"
    job2 = _job("https://www.indeed.com/viewjob?jk=1", location="")
    h2 = await api.hydrate_listing(job2, _client())
    assert h2.found is None and h2.source == "" and job2.location == ""


@pytest.mark.asyncio
async def test_hydrate_listings_preserves_order(monkeypatch):
    jobs = [_job(f"https://jobs.lever.co/acme/{i:08d}-1111-1111-1111-111111111111") for i in range(3)]

    async def fake(job, client):
        return api.Hydration(job, True, "lever")

    monkeypatch.setattr(api, "hydrate_listing", fake)
    out = await api.hydrate_listings(jobs)
    assert [h.job.url for h in out] == [j.url for j in jobs]
