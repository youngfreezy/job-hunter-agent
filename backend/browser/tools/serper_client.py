# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Serper Google Search client -- simple httpx wrapper for google.serper.dev.

Replaces Bright Data MCP's search_engine tool. Stateless REST calls,
no subprocess management, no Node.js dependency.
"""

from __future__ import annotations

import json
import logging

import httpx

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

_SERPER_URL = "https://google.serper.dev/search"
_TIMEOUT = 15.0


async def serper_search(query: str, num_results: int = 10) -> str:
    """Search Google via Serper and return JSON string.

    Returns JSON matching the shape expected by _parse_search_results():
    {"organic": [{"title": "...", "link": "...", "description": "..."}, ...]}
    """
    api_key = get_settings().SERPER_API_KEY
    if not api_key:
        raise RuntimeError(
            "SERPER_API_KEY not set. Get one from google.serper.dev."
        )

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            _SERPER_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": num_results},
        )
        resp.raise_for_status()
        data = resp.json()

    # Normalize: Serper returns "snippet", our parser expects "description"
    for item in data.get("organic", []):
        if "snippet" in item and "description" not in item:
            item["description"] = item.pop("snippet")

    return json.dumps(data)
