"""Job board scrapers for Indeed, LinkedIn, Glassdoor, and Google Jobs.

Each scraper follows the same interface::

    async def scrape_<board>(
        context: BrowserContext,
        search_config: SearchConfig,
        *,
        max_results: int = ...,
    ) -> list[JobListing]

The *context* should be an isolated Playwright BrowserContext obtained from
:class:`~backend.browser.manager.BrowserManager`.
"""

from backend.browser.tools.job_boards.glassdoor import scrape_glassdoor
from backend.browser.tools.job_boards.google_jobs import scrape_google_jobs
from backend.browser.tools.job_boards.indeed import scrape_indeed
from backend.browser.tools.job_boards.linkedin import scrape_linkedin
from backend.browser.tools.job_boards.ziprecruiter import scrape_ziprecruiter

__all__ = [
    "scrape_glassdoor",
    "scrape_google_jobs",
    "scrape_indeed",
    "scrape_linkedin",
    "scrape_ziprecruiter",
]
