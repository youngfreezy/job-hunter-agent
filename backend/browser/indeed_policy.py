"""Boundaries for the Indeed-only Browserbase demo."""
from urllib.parse import urlparse
from backend.shared.models.schemas import SessionConfig


def is_indeed_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "indeed.com" or host.endswith(".indeed.com"))


async def wait_for_indeed_page(page) -> None:
    """Let Browserbase clear a verification interstitial before reading the page."""
    await page.wait_for_function(
        """() => document.body && document.body.innerText.trim().length > 100
          && !/additional verification required|verify you are human|checking your browser|performing security verification/i.test(document.body.innerText)""",
        timeout=45000,
    )


def enforce_indeed_config(request) -> None:
    if request.config is None:
        request.config = SessionConfig()
    if any(not is_indeed_url(url) for url in request.config.job_urls):
        raise ValueError("Indeed-only mode accepts only https://indeed.com job URLs.")
    request.config.job_boards = ["indeed"]
