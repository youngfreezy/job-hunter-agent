"""Boundaries for the Indeed-only Browserbase demo."""
from urllib.parse import urlparse
from backend.shared.models.schemas import SessionConfig


def is_indeed_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "indeed.com" or host.endswith(".indeed.com"))


class IndeedPageUnavailable(ValueError):
    """Safe, actionable listing-read failure; never contains provider details."""

    def __init__(self):
        super().__init__(
            "Indeed did not finish loading after Browserbase's verification wait. "
            "No application was attempted. Check your saved Indeed login in Settings "
            "and retry when the listing is accessible."
        )


async def wait_for_indeed_page(page, *, captcha_monitor=None, since_generation=None) -> None:
    """Bound challenge waiting, then independently require a readable page.

    A solve finishing near the initial cutoff needs a fresh rendering window.
    Solver events only schedule that window; they never prove page readiness.
    """
    from playwright.async_api import TimeoutError as PageTimeout

    predicate = """() => document.body && document.body.innerText.trim().length > 100
          && !/additional verification required|verify you are human|checking your browser|performing security verification/i.test(document.body.innerText)"""
    generation = since_generation if since_generation is not None else (
        captcha_monitor.generation if captcha_monitor else 0
    )
    was_active = bool(captcha_monitor and captcha_monitor.active)
    try:
        await page.wait_for_function(predicate, timeout=45000)
        return
    except PageTimeout:
        # Ignore historical solves from an earlier listing in the same session.
        observed_solve = captcha_monitor and (
            was_active or captcha_monitor.active or captcha_monitor.generation != generation
        )
        if not observed_solve:
            raise IndeedPageUnavailable() from None
    try:
        await captcha_monitor.wait_until_idle(timeout=90)
        await page.wait_for_function(predicate, timeout=30000)
    except (TimeoutError, PageTimeout):
        raise IndeedPageUnavailable() from None


def enforce_indeed_config(request) -> None:
    if request.config is None:
        request.config = SessionConfig()
    if any(not is_indeed_url(url) for url in request.config.job_urls):
        raise ValueError("Indeed-only mode accepts only https://indeed.com job URLs.")
    request.config.job_boards = ["indeed"]


EASY_APPLY_SKIP_REASON = "Indeed Easy Apply only: skipped employer-site application."
EASY_APPLY_LOGIN_SKIP_REASON = "Indeed Easy Apply only: skipped application requiring an additional sign-in."
