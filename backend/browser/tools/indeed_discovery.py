"""Discover Indeed listings through the same cloud Context used for applying."""

from backend.browser.manager import BrowserManager
from backend.browser.tools.job_boards.indeed import scrape_indeed
from backend.shared.event_bus import emit_agent_event
from backend.shared.models.schemas import JobBoard, SearchConfig


async def discover_indeed(*, search_config: SearchConfig, session_id: str,
                          user_id: str, max_results: int,
                          excluded_urls: set[str] | None = None,
                          excluded_companies: set[str] | None = None,
                          excluded_job_keys: set[str] | None = None):
    manager = BrowserManager()
    try:
        await manager.start_for_task(board=JobBoard.INDEED, purpose="discovery", user_id=user_id)
        _, context = await manager.new_context()
        if manager.live_view_url:
            await emit_agent_event(session_id, "browser_live_view", {
                "url": manager.live_view_url,
                "provider": "browserbase",
                "browserbase_session_id": manager.browserbase_session_id,
            })
        return await scrape_indeed(
            context, search_config, max_results=max_results,
            excluded_urls=excluded_urls, excluded_companies=excluded_companies,
            excluded_job_keys=excluded_job_keys,
        )
    finally:
        await manager.stop()
