# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Web search for discovery, with two interchangeable backends.

Discovery asks a search engine for job postings on the ATS hosts (Lever,
Ashby, Greenhouse) and parses the hits.  ``serper_search`` (Google via
Serper) was the only backend; it needs its own paid key.  The Browserbase
Search API (``POST /v1/search``, reference:
https://docs.browserbase.com/reference/api/web-search) answers the same
kind of query with the key the browser sessions already use, so it is the
backend whenever Serper is not configured.

Both backends return the JSON document ``_parse_search_results`` expects:
``{"organic": [{"title", "link", "description"}, ...]}``.  Browserbase
results carry no snippet, so ``description`` holds the publication date
when the API returns one and is otherwise empty; the LLM parser works from
the title and URL, which on ATS hosts name the role and the company.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from backend.browser.tools.serper_client import serper_search
from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

BROWSERBASE_SEARCH_URL = "https://api.browserbase.com/v1/search"
BROWSERBASE_MAX_RESULTS = 25  # documented maximum for numResults
BROWSERBASE_MAX_QUERY_CHARS = 200  # documented maximum for query
_TIMEOUT = 30.0


def search_backend() -> Optional[str]:
    """Which backend ``web_search`` will use: "serper", "browserbase" or None."""
    settings = get_settings()
    if settings.SERPER_API_KEY:
        return "serper"
    if settings.BROWSERBASE_API_KEY:
        return "browserbase"
    return None


def _describe(result: Dict[str, Any]) -> str:
    published = result.get("publishedDate")
    return f"Published {published}" if isinstance(published, str) and published else ""


async def browserbase_search(query: str, num_results: int = 10) -> str:
    """Search the web through Browserbase and return Serper-shaped JSON.

    Sends exactly the documented request body, ``{query, numResults}``, and
    maps each ``results[]`` entry (``url``, ``title``, optional
    ``publishedDate``) onto ``organic[]`` entries with ``link``, ``title``
    and ``description``.  Raises on HTTP errors and on a response without a
    ``results`` list; a malformed answer is never read as "no jobs".
    """
    api_key = get_settings().BROWSERBASE_API_KEY
    if not api_key:
        raise RuntimeError("BROWSERBASE_API_KEY not set")
    body = {
        "query": query[:BROWSERBASE_MAX_QUERY_CHARS],
        "numResults": max(1, min(int(num_results), BROWSERBASE_MAX_RESULTS)),
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            BROWSERBASE_SEARCH_URL,
            headers={"X-BB-API-Key": api_key, "Content-Type": "application/json"},
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        keys = sorted(data.keys()) if isinstance(data, dict) else type(data).__name__
        raise RuntimeError(f"Browserbase search response has no results list (keys: {keys})")
    organic: List[Dict[str, str]] = [
        {
            "title": str(r.get("title") or ""),
            "link": str(r.get("url") or ""),
            "description": _describe(r),
        }
        for r in results
        if isinstance(r, dict) and r.get("url")
    ]
    return json.dumps({"organic": organic})


async def web_search(
    query: str,
    num_results: int = 20,
    tbs: str = "qdr:w",
    page: int = 1,
) -> Optional[str]:
    """Run *query* on the configured backend.

    Serper honours the Google time filter *tbs* and result *page*.  The
    Browserbase Search API has neither, so recency is left to the query text
    and a request for page 2 or later returns None (there is no deeper page
    to fetch) instead of repeating page 1.  Raises RuntimeError when no
    backend is configured.
    """
    backend = search_backend()
    if backend == "serper":
        return await serper_search(query, num_results=num_results, tbs=tbs, page=page)
    if backend == "browserbase":
        if page > 1:
            return None
        return await browserbase_search(query, num_results=num_results)
    raise RuntimeError(
        "No web search backend configured: set SERPER_API_KEY or BROWSERBASE_API_KEY."
    )
