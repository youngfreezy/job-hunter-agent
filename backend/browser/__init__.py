"""Browser automation layer for the JobHunter Agent.

Provides anti-detection browser management via Patchright and job board
scraping tools for Indeed, LinkedIn, Glassdoor, and Google Jobs.
"""

from backend.browser.manager import BrowserManager

__all__ = ["BrowserManager"]
