# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Decide whether a posting's location can serve a requested location.

Discovery used to match on keywords only, so a search for San Francisco
returned the Tokyo and London copies of the same role.  This filter keeps a
posting when its location names the requested city (or a common alias), when
it is remote or country-wide (the scorer and the owner's rules decide whether
remote is acceptable), or when the location is unknown (hydration or the
scorer sorts it out).  A posting that names a different specific place is
dropped.  Requests for "Remote" or no location leave everything through.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional

_REMOTE_TOKENS = ("remote", "anywhere", "distributed", "work from home", "wfh", "united states", "usa", "u.s.")
_UNKNOWN = {"", "unknown", "n/a", "none", "null", "-", "various", "multiple locations", "flexible"}
_GENERIC_REQUESTS = {"", "remote", "anywhere", "united states", "us", "usa"}

# City aliases that appear in postings. Keys are lower-case city names.
_CITY_ALIASES = {
    "san francisco": ("san francisco", "sf bay area", "bay area", "sf, ca", "sf ca", "san fran", "sfo"),
    "new york": ("new york", "nyc", "manhattan", "brooklyn"),
    "new york city": ("new york", "nyc", "manhattan", "brooklyn"),
    "los angeles": ("los angeles", "la, ca", "santa monica"),
    "washington": ("washington, dc", "washington dc", "d.c.", "dc metro"),
    "seattle": ("seattle", "bellevue", "redmond"),
}


def _city(request: str) -> str:
    return request.split(",")[0].strip().lower()


def wanted_terms(locations: Optional[Iterable[str]]) -> List[str]:
    """Lower-case terms a posting location must contain to match the request."""
    terms: List[str] = []
    for loc in locations or []:
        city = _city(loc)
        if city in _GENERIC_REQUESTS:
            continue
        for alias in _CITY_ALIASES.get(city, (city,)):
            if alias not in terms:
                terms.append(alias)
    return terms


def _has_token(text: str, token: str) -> bool:
    # word-ish boundary so "us" does not match "business"
    return re.search(r"(?<![a-z])" + re.escape(token) + r"(?![a-z])", text) is not None


def location_allowed(location: Optional[str], locations: Optional[Iterable[str]]) -> bool:
    """True when *location* can serve a request for *locations*."""
    terms = wanted_terms(locations)
    if not terms:
        return True
    loc = (location or "").strip().lower()
    if loc in _UNKNOWN:
        return True
    if any(_has_token(loc, t) for t in _REMOTE_TOKENS):
        return True
    return any(t in loc for t in terms)
