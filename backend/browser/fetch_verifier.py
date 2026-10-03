# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Discovery verifier built on the Browserbase Fetch API.

Before a scored job enters the shortlist we fetch its page as markdown through
Browserbase (``POST /v1/fetch``), which renders JavaScript and goes through
Browserbase's own IPs instead of ours, and check two things:

1. the requisition is still open (no HTTP error, no "no longer available" copy)
2. the page exposes an Apply control (a link or button whose text is "Apply",
   "Apply now", "Easy Apply", ...)

The verdict is stored on the JobListing as ``verified_open`` / ``verify_note``.
Jobs the verifier positively finds closed or apply-less are removed from the
shortlist.  Jobs it could not check (verifier disabled, API error) stay, with
the reason in ``verify_note``: an outage must not empty every shortlist, but it
is never hidden.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

from backend.browser.browserbase_client import (
    API_BASE,
    BrowserbaseConfig,
    BrowserbaseError,
    _headers,
    config_for_user,
)
from backend.shared.config import settings
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import JobListing

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 45
VERIFY_CONCURRENCY = 4
# How many candidates past the session's max_jobs cap we verify, so a few
# closed listings do not leave the shortlist short.
VERIFY_HEADROOM = 10

# Copy that ATS pages and boards show for closed requisitions.
_CLOSED_INDICATORS: Tuple[str, ...] = (
    "no longer available",
    "no longer accepting applications",
    "no longer accepting",
    "this job has expired",
    "this posting has expired",
    "job posting has expired",
    "position has been filled",
    "this position has been filled",
    "this job is closed",
    "this position is closed",
    "job is closed",
    "this job has been closed",
    "this job has been removed",
    "job not found",
    "posting not found",
    "the job you are looking for is no longer",
    "this opportunity is no longer",
    "we are no longer accepting",
    "applications for this role are closed",
)

# An Apply control in markdown: a link whose text is an apply phrase, or a
# line that is only an apply phrase (buttons usually render as bare text).
_APPLY_PHRASE = r"(?:easy apply|quick apply|apply now|apply today|apply here|apply for this (?:job|role|position)|apply to (?:this )?(?:job|role|position)|apply on company (?:site|website)|apply|submit application|start application)"
_APPLY_LINK_RE = re.compile(r"\[\s*[^\]]*?\b" + _APPLY_PHRASE + r"\b[^\]]*?\s*\]\(", re.IGNORECASE)
_APPLY_LINE_RE = re.compile(r"^\W*" + _APPLY_PHRASE + r"\W*$", re.IGNORECASE | re.MULTILINE)


@dataclass
class FetchResult:
    markdown: str
    status_code: Optional[int] = None
    final_url: Optional[str] = None


def verifier_disabled_reason(config: Optional[BrowserbaseConfig] = None) -> Optional[str]:
    """Why the verifier will not run right now, or None when it will."""
    if not settings.BROWSERBASE_VERIFY_LISTINGS:
        return "verifier disabled (BROWSERBASE_VERIFY_LISTINGS=false)"
    api_key = config.api_key if config is not None else settings.BROWSERBASE_API_KEY
    if not api_key:
        return "verifier skipped: BROWSERBASE_API_KEY not set"
    return None


def _extract_markdown(data: Any) -> Optional[str]:
    """Pull the markdown body out of a Fetch API response.

    TODO(unverified): the response field names below are not confirmed against
    the Browserbase Fetch API reference (docs were unreachable when this was
    written).  Unknown shapes raise instead of being treated as an empty page.
    """
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return None
    for key in ("markdown", "content", "text"):
        value = data.get(key)
        if isinstance(value, str):
            return value
    for key in ("data", "result"):
        nested = data.get(key)
        if isinstance(nested, dict):
            found = _extract_markdown(nested)
            if found is not None:
                return found
    return None


def _extract_int(data: Any, keys: Iterable[str]) -> Optional[int]:
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if isinstance(value, int):
            return value
    for key in ("data", "result"):
        nested = data.get(key)
        if isinstance(nested, dict):
            found = _extract_int(nested, keys)
            if found is not None:
                return found
    return None


def _extract_str(data: Any, keys: Iterable[str]) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            return value
    for key in ("data", "result"):
        nested = data.get(key)
        if isinstance(nested, dict):
            found = _extract_str(nested, keys)
            if found is not None:
                return found
    return None


async def fetch_markdown(url: str, config: Optional[BrowserbaseConfig] = None) -> FetchResult:
    """Render *url* through the Browserbase Fetch API and return its markdown.

    TODO(unverified): request body field names (``url``, ``format``) follow
    the owner's description of the endpoint, not the published reference.
    A response without a markdown body raises BrowserbaseError so a schema
    mismatch surfaces as an error on every listing, never as "verified".
    """
    project_id = config.project_id if config is not None else settings.BROWSERBASE_PROJECT_ID
    body: Dict[str, Any] = {"url": url, "format": "markdown"}
    if project_id:
        body["projectId"] = project_id
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
        r = await client.post(f"{API_BASE}/fetch", headers=_headers(config), json=body)
    if r.status_code >= 400:
        raise BrowserbaseError(f"fetch failed: {r.status_code} {r.text[:200]}")
    try:
        data = r.json()
    except ValueError:
        data = r.text
    markdown = _extract_markdown(data)
    if markdown is None:
        keys = sorted(data.keys()) if isinstance(data, dict) else type(data).__name__
        raise BrowserbaseError(f"fetch response has no markdown body (keys: {keys})")
    return FetchResult(
        markdown=markdown,
        status_code=_extract_int(data, ("statusCode", "status_code", "status")),
        final_url=_extract_str(data, ("finalUrl", "final_url", "url")),
    )


def judge_listing(result: FetchResult) -> Tuple[bool, str]:
    """Decide whether a fetched page is an open requisition with an Apply control.

    Returns (verified_open, note).  The note always says what decided it.
    """
    if result.status_code is not None and result.status_code >= 400:
        return False, f"closed: page returned HTTP {result.status_code}"

    text = result.markdown or ""
    lowered = text.lower()
    if not lowered.strip():
        return False, "closed: page rendered empty"

    for phrase in _CLOSED_INDICATORS:
        if phrase in lowered:
            return False, f"closed: page says '{phrase}'"

    link = _APPLY_LINK_RE.search(text)
    if link:
        label = link.group(0).strip("[]( \n")[:60]
        return True, f"open: apply link '{label}'"
    line = _APPLY_LINE_RE.search(text)
    if line:
        return True, f"open: apply control '{line.group(0).strip()[:60]}'"
    return False, "no Apply control found in page text"


async def verify_listing(job: JobListing, config: Optional[BrowserbaseConfig] = None) -> JobListing:
    """Verify one job in place. Errors are recorded in verify_note, not raised."""
    url = job.external_apply_url or job.url
    try:
        fetched = await fetch_markdown(url, config)
    except (BrowserbaseError, httpx.HTTPError) as exc:
        job.verified_open = False
        job.verify_note = f"verifier error: {str(exc)[:160]}"
        logger.warning("Listing verifier failed for %s (%s): %s", job.title, url, exc)
        return job
    job.verified_open, job.verify_note = judge_listing(fetched)
    logger.info("Listing verifier: %s @ %s -> %s", job.title, job.company, job.verify_note)
    return job


def _is_positively_closed(job: JobListing) -> bool:
    """True only when the verifier ran and found the listing closed or apply-less."""
    if job.verified_open:
        return False
    note = job.verify_note or ""
    return note.startswith("closed:") or note.startswith("no Apply control")


async def verify_shortlist_candidates(
    scored_jobs: List[Any],
    session_id: str = "",
    limit: Optional[int] = None,
    user_id: Optional[str] = None,
) -> List[Any]:
    """Verify the top *limit* scored jobs and drop the ones found closed.

    *scored_jobs* are ScoredJob objects (``.job`` is the JobListing), already
    sorted by score.  Jobs past *limit* are left unverified with a note.
    *user_id* selects that user's Browserbase credentials when they saved any.
    """
    if not scored_jobs:
        return scored_jobs

    config = config_for_user(user_id)
    disabled = verifier_disabled_reason(config)
    if disabled:
        for sj in scored_jobs:
            sj.job.verified_open = False
            sj.job.verify_note = disabled
        logger.info("Listing verifier not run for %d jobs: %s", len(scored_jobs), disabled)
        return scored_jobs

    to_verify = scored_jobs if limit is None else scored_jobs[:limit]
    for sj in scored_jobs[len(to_verify):]:
        sj.job.verified_open = False
        sj.job.verify_note = "not verified: beyond verification budget"

    semaphore = asyncio.Semaphore(VERIFY_CONCURRENCY)

    async def _one(sj: Any) -> None:
        async with semaphore:
            await verify_listing(sj.job, config)

    if session_id:
        await emit_agent_event(session_id, "scoring_progress", {
            "step": f"Verifying {len(to_verify)} listings are open via Browserbase...",
        })
    await asyncio.gather(*[_one(sj) for sj in to_verify])

    kept = [sj for sj in scored_jobs if not _is_positively_closed(sj.job)]
    removed = len(scored_jobs) - len(kept)
    verified = sum(1 for sj in to_verify if sj.job.verified_open)
    logger.info(
        "Listing verifier: %d verified open, %d removed, %d unverified (session %s)",
        verified, removed, len(kept) - verified, session_id or "-",
    )
    if session_id:
        await emit_agent_event(session_id, "listing_verification", {
            "checked": len(to_verify),
            "verified_open": verified,
            "removed": removed,
            "removed_jobs": [
                {"job_id": str(sj.job.id), "title": sj.job.title, "company": sj.job.company,
                 "note": sj.job.verify_note}
                for sj in scored_jobs if _is_positively_closed(sj.job)
            ],
        })
    return kept
