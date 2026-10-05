# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Hydrate discovered listings from the ATS vendors' public posting APIs.

Search results name a posting only by title and URL, so the scorer sees no
location, pay or description and cannot apply location rules.  Lever,
Greenhouse and Ashby all publish the posting itself as JSON without
authentication:

- Lever:      https://api.lever.co/v0/postings/{org}/{id}
- Greenhouse: https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{id}
- Ashby:      https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true

``hydrate_listings`` fills location, remote flag, pay range and a description
snippet from those documents and reports postings the vendor no longer serves
(404) as gone so discovery can drop them before scoring.  A vendor error or
an unknown URL leaves the listing exactly as it was.
"""

from __future__ import annotations

import asyncio
import html as _html
import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx

from backend.shared.models.schemas import JobListing

logger = logging.getLogger(__name__)

LEVER_POSTING_URL = "https://api.lever.co/v0/postings/{org}/{posting_id}"
GREENHOUSE_JOB_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
ASHBY_BOARD_URL = "https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true"

_TIMEOUT = 20.0
_CONCURRENCY = 6
_SNIPPET_CHARS = 500

_LEVER_RE = re.compile(r"^https?://jobs\.lever\.co/([^/?#]+)/([0-9a-f-]{36})", re.IGNORECASE)
_GREENHOUSE_RE = re.compile(
    r"^https?://(?:job-boards|boards)\.greenhouse\.io/([^/?#]+)/jobs/(\d+)", re.IGNORECASE
)
_GREENHOUSE_EMBED_RE = re.compile(r"[?&]gh_jid=(\d+)", re.IGNORECASE)
_ASHBY_RE = re.compile(r"^https?://jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f-]{36})", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_UNKNOWN_LOCATIONS = {"", "unknown", "n/a", "none", "null", "-"}


@dataclass(frozen=True)
class PostingRef:
    ats: str  # "lever" | "greenhouse" | "ashby"
    org: str
    posting_id: str


@dataclass
class Hydration:
    job: JobListing
    found: Optional[bool]  # True: vendor returned it; False: vendor says gone (404); None: not checked / error
    source: str = ""


def parse_posting_ref(url: str) -> Optional[PostingRef]:
    """Identify the vendor, organisation and posting id in an ATS URL."""
    m = _LEVER_RE.match(url or "")
    if m:
        return PostingRef("lever", m.group(1), m.group(2).lower())
    m = _GREENHOUSE_RE.match(url or "")
    if m:
        return PostingRef("greenhouse", m.group(1), m.group(2))
    m = _ASHBY_RE.match(url or "")
    if m:
        return PostingRef("ashby", m.group(1), m.group(2).lower())
    return None


def _snippet(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    plain = _html.unescape(_TAG_RE.sub(" ", _html.unescape(text)))
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain[:_SNIPPET_CHARS] or None


def _is_unknown_location(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in _UNKNOWN_LOCATIONS


def _apply(job: JobListing, *, location: Optional[str], is_remote: Optional[bool],
           salary: Optional[str], description: Optional[str], title: Optional[str] = None,
           company: Optional[str] = None) -> None:
    if location and location.strip():
        job.location = location.strip()
    if is_remote is not None:
        job.is_remote = bool(is_remote)
    elif job.location and any(t in job.location.lower() for t in ("remote", "anywhere")):
        job.is_remote = True
    if salary and not job.salary_range:
        job.salary_range = salary
    if description and not job.description_snippet:
        job.description_snippet = description
    if title and title.strip() and (not job.title or job.title.strip().lower() in ("", "unknown")):
        job.title = title.strip()
    if company and company.strip() and (not job.company or job.company.strip().lower() in ("", "unknown")):
        job.company = company.strip()


def _lever_salary(sr: Any) -> Optional[str]:
    if not isinstance(sr, dict):
        return None
    lo, hi = sr.get("min"), sr.get("max")
    if not lo and not hi:
        return None
    cur = sr.get("currency") or "USD"
    interval = sr.get("interval") or ""
    rng = f"{lo:,}" if lo else "?"
    if hi:
        rng += f" - {hi:,}"
    return f"{cur} {rng}" + (f" per {interval.replace('-', ' ')}" if interval else "")


def _lever_location(data: Dict[str, Any]) -> Optional[str]:
    cats = data.get("categories") or {}
    locs = cats.get("allLocations") if isinstance(cats.get("allLocations"), list) else None
    if locs:
        return " | ".join(str(x) for x in locs if x)
    return cats.get("location") or None


async def _hydrate_lever(job: JobListing, ref: PostingRef, client: httpx.AsyncClient) -> Hydration:
    r = await client.get(LEVER_POSTING_URL.format(org=ref.org, posting_id=ref.posting_id))
    if r.status_code == 404:
        return Hydration(job, False, "lever")
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise ValueError("lever posting is not an object")
    workplace = (data.get("workplaceType") or "").lower()
    location = _lever_location(data)
    if workplace in ("remote", "hybrid") and location and workplace not in location.lower():
        location = f"{location} ({workplace})"
    _apply(
        job,
        location=location,
        is_remote=True if workplace == "remote" else (False if workplace in ("onsite", "on-site", "hybrid") else None),
        salary=_lever_salary(data.get("salaryRange")),
        description=_snippet(data.get("descriptionPlain") or data.get("description")),
        title=data.get("text"),
    )
    return Hydration(job, True, "lever")


async def _hydrate_greenhouse(job: JobListing, ref: PostingRef, client: httpx.AsyncClient) -> Hydration:
    r = await client.get(GREENHOUSE_JOB_URL.format(board=ref.org, job_id=ref.posting_id))
    if r.status_code == 404:
        return Hydration(job, False, "greenhouse")
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise ValueError("greenhouse job is not an object")
    location = (data.get("location") or {}).get("name") if isinstance(data.get("location"), dict) else None
    offices = data.get("offices") if isinstance(data.get("offices"), list) else []
    if not location and offices:
        location = " | ".join(str(o.get("name")) for o in offices if isinstance(o, dict) and o.get("name"))
    salary = None
    for meta in data.get("metadata") or []:
        if isinstance(meta, dict) and meta.get("value") and any(
            k in str(meta.get("name", "")).lower() for k in ("salary", "compensation", "pay range")
        ):
            salary = str(meta["value"])
            break
    _apply(
        job,
        location=location,
        is_remote=None,
        salary=salary,
        description=_snippet(data.get("content")),
        title=data.get("title"),
        company=data.get("company_name"),
    )
    return Hydration(job, True, "greenhouse")


_ASHBY_CACHE_TTL_SECONDS = 300
_ASHBY_CACHE_MAX_BOARDS = 128
_ashby_board_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()


async def _ashby_board(org: str, client: httpx.AsyncClient) -> Any:
    key = org.lower()
    cached = _ashby_board_cache.get(key)
    if cached is not None:
        expires_at, data = cached
        if time.monotonic() < expires_at:
            _ashby_board_cache.move_to_end(key)
            return data
        del _ashby_board_cache[key]
    r = await client.get(ASHBY_BOARD_URL.format(org=org))
    if r.status_code == 404:
        data = None
    else:
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            raise ValueError("ashby board has no jobs list")
    _ashby_board_cache[key] = (time.monotonic() + _ASHBY_CACHE_TTL_SECONDS, data)
    _ashby_board_cache.move_to_end(key)
    while len(_ashby_board_cache) > _ASHBY_CACHE_MAX_BOARDS:
        _ashby_board_cache.popitem(last=False)
    return data


def _ashby_salary(comp: Any) -> Optional[str]:
    if not isinstance(comp, dict):
        return None
    for key in ("compensationTierSummary", "scrapeableCompensationSalarySummary"):
        value = comp.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


async def _hydrate_ashby(job: JobListing, ref: PostingRef, client: httpx.AsyncClient) -> Hydration:
    board = await _ashby_board(ref.org, client)
    if board is None:
        return Hydration(job, False, "ashby")
    jobs = board.get("jobs") if isinstance(board, dict) else None
    if not isinstance(jobs, list):
        raise ValueError("ashby board has no jobs list")
    match = next((j for j in jobs if isinstance(j, dict) and str(j.get("id", "")).lower() == ref.posting_id), None)
    if match is None:
        # The board is served but no longer lists this posting.
        return Hydration(job, False, "ashby")
    location = match.get("location")
    secondary = match.get("secondaryLocations") if isinstance(match.get("secondaryLocations"), list) else []
    extra = [s.get("location") for s in secondary if isinstance(s, dict) and s.get("location")]
    if location and extra:
        location = " | ".join([str(location)] + [str(x) for x in extra])
    if match.get("isRemote") and location and "remote" not in str(location).lower():
        location = f"{location} (remote)"
    _apply(
        job,
        location=location,
        is_remote=bool(match.get("isRemote")) if match.get("isRemote") is not None else None,
        salary=_ashby_salary(match.get("compensation")),
        description=_snippet(match.get("descriptionPlain") or match.get("descriptionHtml")),
        title=match.get("title"),
    )
    return Hydration(job, True, "ashby")


async def hydrate_listing(job: JobListing, client: httpx.AsyncClient) -> Hydration:
    """Fill *job* from its vendor's posting API. Never raises."""
    ref = parse_posting_ref(job.external_apply_url or job.url)
    if ref is None:
        return Hydration(job, None, "")
    try:
        if ref.ats == "lever":
            return await _hydrate_lever(job, ref, client)
        if ref.ats == "greenhouse":
            return await _hydrate_greenhouse(job, ref, client)
        return await _hydrate_ashby(job, ref, client)
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("Posting API hydration skipped for %s (%s): %s", job.url, ref.ats, str(exc)[:120])
        return Hydration(job, None, ref.ats)


async def hydrate_listings(jobs: List[JobListing], concurrency: int = _CONCURRENCY) -> List[Hydration]:
    """Hydrate every listing concurrently; order is preserved."""
    if not jobs:
        return []
    semaphore = asyncio.Semaphore(max(1, concurrency))
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        async def _one(job: JobListing) -> Hydration:
            async with semaphore:
                return await hydrate_listing(job, client)
        return list(await asyncio.gather(*[_one(j) for j in jobs]))


def unknown_location(job: JobListing) -> bool:
    return _is_unknown_location(job.location)
