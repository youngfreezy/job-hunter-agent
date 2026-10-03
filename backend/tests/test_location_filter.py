"""Requested-location filter for discovered postings."""

from __future__ import annotations

import pytest

from backend.browser.tools.job_boards import greenhouse_boards, lever_boards
from backend.browser.tools.job_boards.location_filter import location_allowed, wanted_terms


def test_wanted_terms_expand_city_aliases_and_skip_generic_requests():
    assert "bay area" in wanted_terms(["San Francisco, CA"])
    assert wanted_terms(["Remote"]) == []
    assert wanted_terms(["United States"]) == []
    assert wanted_terms(["Austin, TX"]) == ["austin"]


@pytest.mark.parametrize("location,ok", [
    ("San Francisco, CA", True),
    ("SF Bay Area", True),
    ("San Francisco, CA | New York City, NY", True),
    ("Remote - US", True),
    ("United States", True),
    ("Unknown", True),
    ("", True),
    ("Tokyo, Japan", False),
    ("London, United Kingdom", False),
    ("New York, NY", False),
    ("Remoto", False),  # not a recognised remote token; the scorer never sees it
])
def test_location_allowed_for_a_city_request(location, ok):
    assert location_allowed(location, ["San Francisco, CA"]) is ok


def test_everything_allowed_without_a_city_request():
    assert location_allowed("Tokyo, Japan", ["Remote"]) is True
    assert location_allowed("Tokyo, Japan", None) is True


def test_greenhouse_matcher_drops_other_cities_for_a_city_request():
    tokyo = {"title": "Applied AI Engineer", "location": {"name": "Tokyo, Japan"}}
    sf = {"title": "Applied AI Engineer", "location": {"name": "San Francisco, CA"}}
    assert greenhouse_boards._matches_keywords(tokyo, ["Applied AI Engineer"], False, ["San Francisco, CA"]) is False
    assert greenhouse_boards._matches_keywords(sf, ["Applied AI Engineer"], False, ["San Francisco, CA"]) is True
    # no location request: unchanged behaviour
    assert greenhouse_boards._matches_keywords(tokyo, ["Applied AI Engineer"], False) is True


def test_lever_matcher_drops_other_cities_and_keeps_remote():
    london = {"text": "Backend Software Engineer", "categories": {"location": "London, United Kingdom"}}
    remote = {"text": "AI Engineer", "categories": {"location": "Anywhere"}, "workplaceType": "remote"}
    assert lever_boards._matches_keywords(london, ["Software Engineer"], False, ["San Francisco, CA"]) is False
    assert lever_boards._matches_keywords(remote, ["AI Engineer"], False, ["San Francisco, CA"]) is True
