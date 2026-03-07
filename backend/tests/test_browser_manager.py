from backend.browser.manager import build_brightdata_cdp_url, should_use_brightdata
from backend.shared.config import settings


def test_build_brightdata_cdp_url_prefers_explicit_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "BRIGHT_DATA_BROWSER_CDP_URL", "wss://custom-endpoint", raising=False)
    monkeypatch.setattr(settings, "BRIGHT_DATA_BROWSER_USERNAME", None, raising=False)
    monkeypatch.setattr(settings, "BRIGHT_DATA_BROWSER_PASSWORD", None, raising=False)

    assert build_brightdata_cdp_url() == "wss://custom-endpoint"


def test_build_brightdata_cdp_url_uses_credentials(monkeypatch):
    monkeypatch.setattr(settings, "BRIGHT_DATA_BROWSER_CDP_URL", None, raising=False)
    monkeypatch.setattr(settings, "BRIGHT_DATA_BROWSER_USERNAME", "user", raising=False)
    monkeypatch.setattr(settings, "BRIGHT_DATA_BROWSER_PASSWORD", "pass", raising=False)
    monkeypatch.setattr(settings, "BRIGHT_DATA_BROWSER_HOST", "brd.superproxy.io", raising=False)
    monkeypatch.setattr(settings, "BRIGHT_DATA_BROWSER_PORT", 9222, raising=False)

    assert build_brightdata_cdp_url() == "wss://user:pass@brd.superproxy.io:9222"


def test_should_use_brightdata_only_for_targeted_apply_boards(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_PROVIDER", "brightdata", raising=False)
    monkeypatch.setattr(settings, "BRIGHT_DATA_BROWSER_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "BRIGHT_DATA_BROWSER_FORCE", False, raising=False)
    monkeypatch.setattr(
        settings,
        "BRIGHT_DATA_BROWSER_BOARDS",
        "greenhouse,workday,lever,ashby",
        raising=False,
    )
    monkeypatch.setattr(settings, "BRIGHT_DATA_BROWSER_USE_FOR_DISCOVERY", False, raising=False)

    assert should_use_brightdata(board="greenhouse", purpose="apply") is True
    assert should_use_brightdata(board="linkedin", purpose="apply") is False
    assert should_use_brightdata(board="greenhouse", purpose="discovery") is False


def test_should_use_brightdata_force_mode(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_PROVIDER", "brightdata", raising=False)
    monkeypatch.setattr(settings, "BRIGHT_DATA_BROWSER_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "BRIGHT_DATA_BROWSER_FORCE", True, raising=False)

    assert should_use_brightdata(board="linkedin", purpose="apply") is True
