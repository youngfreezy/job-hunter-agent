"""Stagehand v4 on the same account-scoped Browserbase browser used by the UI.

The SDK installs its browser extension at session creation; it cannot be added
to an already-running cloud browser. BrowserManager owns this lifecycle.
https://docs.stagehand.dev/v4/configuration/browser
"""

from contextlib import AsyncExitStack

import httpx
from stagehand import Stagehand, browserbase

from backend.browser.browserbase_client import BrowserbaseConfig, BrowserbaseSession
from backend.shared.config import get_settings
from backend.shared.llm import anthropic_default_headers, default_model, get_llm_provider


async def launch_stagehand(config: BrowserbaseConfig, context_id: str):
    settings = get_settings()
    provider = get_llm_provider()
    key = settings.ANTHROPIC_API_KEY if provider == "anthropic" else settings.OPENAI_API_KEY
    if not key or not config.api_key or not context_id:
        raise RuntimeError("Stagehand requires model credentials and your saved Indeed login.")
    cleanup = AsyncExitStack()
    try:
        browser = await browserbase.launch(
            api_key=config.api_key, proxies=config.proxies,
            timeout=config.session_timeout,
            browser_settings={
                "context": {"id": context_id, "persist": True},
                "solve_captchas": True,
            },
        )
        cleanup.push_async_callback(browser.close)
        agent = await Stagehand.create(
            browser=browser, model=f"{provider}/{default_model()}",
            model_api_key=key,
            model_headers=anthropic_default_headers() if provider == "anthropic" else None,
            logging={"level": "off"},  # Prompts contain applicant personal information.
            self_heal=True,
        )
        cleanup.push_async_callback(agent.close)
        headers = {"X-BB-API-Key": config.api_key}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"https://api.browserbase.com/v1/sessions/{browser.session_id}", headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            debug = await client.get(
                f"https://api.browserbase.com/v1/sessions/{browser.session_id}/debug", headers=headers,
            )
            debug.raise_for_status()
        info = BrowserbaseSession(
            id=browser.session_id, connect_url=data["connectUrl"], context_id=context_id,
            live_view_url=debug.json().get("debuggerFullscreenUrl") or debug.json().get("debuggerUrl"),
        )
        return agent, info, cleanup
    except BaseException:
        await cleanup.aclose()
        raise
