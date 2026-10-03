# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Discovery verifier built on the Browserbase Fetch API.

Before a scored job enters the shortlist we fetch its page as markdown through
Browserbase (``POST /v1/fetch``, reference:
https://docs.browserbase.com/reference/api/fetch-a-page), which goes through
Browserbase's own IPs instead of ours, and check two things:

1. the requisition is still open (no HTTP error, no "no longer available" copy)
2. the page exposes an Apply control (a link or button whose text is "Apply",
   "Apply now", "Easy Apply", ...)

The verdict is stored on the JobListing as ``verified_open`` / ``verify_note``.
Jobs the verifier positively finds closed or apply-less are removed from the
shortlist.  Jobs it could not check (verifier disabled, API error, upstream
block, a page too thin to judge) stay, with the reason in ``verify_note``: an
outage must not empty every shortlist, but it is never hidden.

Fetch does not execute JavaScript and returns at most 5 MB, so a page that is
rendered client-side comes back as a near-empty shell.  Such pages are
reported as unverified, never as closed.  ``format: "markdown"`` (Fetch
Extract) has to be enabled on the Browserbase project; when it is not (HTTP
402/403) the verifier fetches the raw HTML instead and reduces it to text
itself.
"""

from __future__ import annotations

import asyncio
import html as _html
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
    _resolve,
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
# Below this many characters of text a page without an Apply control is more
# likely a client-rendered shell (Fetch runs no JavaScript) than an apply-less
# requisition, so it is left unverified instead of being dropped.
MIN_TEXT_CHARS = 300

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
    content_type: Optional[str] = None
    source_format: str = "markdown"  # "markdown" or "raw" (HTML reduced locally)


def verifier_disabled_reason(config: Optional[BrowserbaseConfig] = None) -> Optional[str]:
    """Why the verifier will not run right now, or None when it will."""
    if not settings.BROWSERBASE_VERIFY_LISTINGS:
        return "verifier disabled (BROWSERBASE_VERIFY_LISTINGS=false)"
    api_key = config.api_key if config is not None else settings.BROWSERBASE_API_KEY
    if not api_key:
        return "verifier skipped: BROWSERBASE_API_KEY not set"
    return None


_TAG_SCRIPT_RE = re.compile(r"<(script|style|svg|head)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_TAG_ANCHOR_RE = re.compile(r"<a\b[^>]*?href\s*=\s*([\"\'])(.*?)\1[^>]*>(.*?)</a\s*>", re.IGNORECASE | re.DOTALL)
_TAG_BUTTON_RE = re.compile(r"<(button|input)\b([^>]*)>(.*?)(?:</button\s*>|$)", re.IGNORECASE | re.DOTALL)
_TAG_INPUT_VALUE_RE = re.compile(r"value\s*=\s*([\"\'])(.*?)\1", re.IGNORECASE)
_TAG_BLOCK_RE = re.compile(
    r"</?(?:p|div|br|li|ul|ol|h[1-6]|tr|td|th|section|article|header|footer|nav|main|aside|form|label|span)\b[^>]*>",
    re.IGNORECASE,
)
_TAG_ANY_RE = re.compile(r"<[^>]+>")


def _strip_tags(fragment: str) -> str:
    return _html.unescape(_TAG_ANY_RE.sub(" ", fragment))


def _html_to_markdown(raw: str) -> str:
    """Reduce an HTML document to the text the judge needs.

    Used when the Browserbase project has no markdown (Fetch Extract)
    enablement.  Anchors become ``[text](href)`` so ``_APPLY_LINK_RE`` still
    applies, buttons and inputs become their own line, block elements become
    line breaks, everything else is stripped.
    """
    text = _TAG_SCRIPT_RE.sub(" ", raw)
    text = _TAG_ANCHOR_RE.sub(lambda m: f" [{_strip_tags(m.group(3)).strip()}]({m.group(2).strip()}) ", text)

    def _button(m: "re.Match[str]") -> str:
        if m.group(1).lower() == "input":
            value = _TAG_INPUT_VALUE_RE.search(m.group(2) or "")
            return f"\n{_html.unescape(value.group(2))}\n" if value else "\n"
        return f"\n{_strip_tags(m.group(3)).strip()}\n"

    text = _TAG_BUTTON_RE.sub(_button, text)
    text = _TAG_BLOCK_RE.sub("\n", text)
    text = _strip_tags(text)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _request_body(url: str, fmt: str, cfg: BrowserbaseConfig) -> Dict[str, Any]:
    body: Dict[str, Any] = {"url": url, "format": fmt, "allowRedirects": True}
    if cfg.proxies:
        body["proxies"] = True
    return body


def _parse_fetch_response(r: httpx.Response) -> Tuple[str, Optional[int], Optional[str]]:
    """Return (content, statusCode, contentType) from a 200 Fetch response."""
    try:
        data = r.json()
    except ValueError as exc:
        raise BrowserbaseError(f"fetch response is not JSON: {r.text[:120]!r}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("content"), str):
        keys = sorted(data.keys()) if isinstance(data, dict) else type(data).__name__
        raise BrowserbaseError(f"fetch response has no string content (keys: {keys})")
    status_code = data.get("statusCode")
    content_type = data.get("contentType")
    return (
        data["content"],
        status_code if isinstance(status_code, int) else None,
        content_type if isinstance(content_type, str) else None,
    )


async def fetch_markdown(url: str, config: Optional[BrowserbaseConfig] = None) -> FetchResult:
    """Fetch *url* through the Browserbase Fetch API and return it as markdown.

    Request and response shapes follow the published reference: the body is
    ``{url, format, allowRedirects, proxies}`` and a 200 response carries the
    page in ``content`` (a string for ``markdown`` and ``raw``) with the
    upstream ``statusCode`` and ``contentType``.  Redirects are followed
    because job URLs routinely redirect to the live posting.

    When the project cannot use ``format: "markdown"`` (402 quota, 403 not
    enabled) the raw HTML is fetched instead and reduced to text locally, so
    the verifier keeps working on any plan.  Any other error raises
    BrowserbaseError: an unreadable response is an error on the listing,
    never a verdict.
    """
    cfg = _resolve(config)
    headers = _headers(cfg)
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
        r = await client.post(f"{API_BASE}/fetch", headers=headers, json=_request_body(url, "markdown", cfg))
        if r.status_code in (402, 403):
            logger.info(
                "Browserbase Fetch markdown format unavailable (%s): fetching raw HTML for %s",
                r.status_code, url,
            )
            r = await client.post(f"{API_BASE}/fetch", headers=headers, json=_request_body(url, "raw", cfg))
            if r.status_code >= 400:
                raise BrowserbaseError(f"fetch failed: {r.status_code} {r.text[:200]}")
            content, status_code, content_type = _parse_fetch_response(r)
            if content_type and "html" not in content_type.lower() and "text" not in content_type.lower():
                raise BrowserbaseError(f"fetch returned non-text content ({content_type})")
            return FetchResult(
                markdown=_html_to_markdown(content),
                status_code=status_code,
                content_type=content_type,
                source_format="raw",
            )
    if r.status_code >= 400:
        raise BrowserbaseError(f"fetch failed: {r.status_code} {r.text[:200]}")
    content, status_code, content_type = _parse_fetch_response(r)
    return FetchResult(markdown=content, status_code=status_code, content_type=content_type)


def judge_listing(result: FetchResult) -> Tuple[bool, str]:
    """Decide whether a fetched page is an open requisition with an Apply control.

    Returns (verified_open, note).  The note always says what decided it, and
    only notes starting with ``closed:`` or ``no Apply control`` count as a
    positive finding that removes the listing (see ``_is_positively_closed``).
    HTTP 404/410 mean the posting is gone; every other upstream error (a bot
    block, an outage) and a page with too little text to judge are reported as
    unverified, because Fetch runs no JavaScript and cannot tell a
    client-rendered posting from an empty one.
    """
    sc = result.status_code
    if sc is not None:
        if sc in (404, 410):
            return False, f"closed: page returned HTTP {sc}"
        if sc >= 400:
            return False, f"unverified: page returned HTTP {sc}"

    text = result.markdown or ""
    lowered = text.lower()
    if not lowered.strip():
        return False, "unverified: page has no text (client-rendered or blocked)"

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
    if len(lowered.strip()) < MIN_TEXT_CHARS:
        return False, f"unverified: page too thin to judge ({len(lowered.strip())} chars, likely client-rendered)"
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
