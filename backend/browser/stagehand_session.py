"""Stagehand v4 on the same account-scoped Browserbase browser used by the UI.

The SDK installs its browser extension at session creation; it cannot be added
to an already-running cloud browser. BrowserManager owns this lifecycle.
https://docs.stagehand.dev/v4/configuration/browser
"""

import asyncio
from contextlib import AsyncExitStack
from ipaddress import ip_address
from urllib.parse import urlsplit

import httpx
from browserbase import AsyncBrowserbase, omit
from stagehand import Stagehand, browserbase
from stagehand.extension_assets import build_extension_archive

from backend.browser.browserbase_client import BrowserbaseConfig, BrowserbaseSession
from backend.shared.model_access import current_model_credentials, current_model_user, model_user_scope
from backend.browser.stagehand_model import generate
from backend.gateway.routes.stagehand_telemetry import STAGEHAND_TELEMETRY_PATH
from backend.shared.config import settings


def _telemetry_config() -> dict:
    """Keep SDK traces on our discard endpoint, never its example.com default."""
    error = "Stagehand requires BACKEND_PUBLIC_URL to be a public HTTPS origin."
    origin = settings.BACKEND_PUBLIC_URL
    if not origin or origin != origin.strip() or "\\" in origin:
        raise RuntimeError(error)
    try:
        parsed = urlsplit(origin)
        hostname = parsed.hostname or ""
        port = parsed.port  # Validate malformed ports before allocating a session.
    except ValueError:
        raise RuntimeError(error) from None
    if (
        parsed.scheme != "https" or not hostname or "." not in hostname
        or parsed.username is not None or parsed.password is not None
        or parsed.path not in ("", "/") or parsed.query or parsed.fragment
        or any(character.isspace() for character in origin)
        or hostname.rstrip(".").lower() in ("localhost", "example.com")
        or hostname.rstrip(".").lower().endswith((".localhost", ".local", ".example.com"))
        or (port is not None and port != 443)
    ):
        raise RuntimeError(error)
    try:
        address = ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise RuntimeError(error)
    return {"traces": {
        "endpoint": origin.rstrip("/") + STAGEHAND_TELEMETRY_PATH,
        "headers": {},
    }}


async def launch_stagehand(config: BrowserbaseConfig, context_id: str):
    credentials = current_model_credentials()
    key = credentials.api_key
    model_user_id = current_model_user()
    if not key or not config.api_key or not config.project_id or not context_id:
        raise RuntimeError("Stagehand requires model credentials, a Browserbase project, and your saved Indeed login.")
    # Stagehand 4.1 always exports traces, including prompt data even when logs
    # are off. Validate our no-storage sink before creating paid resources.
    telemetry = _telemetry_config()
    cleanup = AsyncExitStack()
    try:
        # Stagehand 4.1 launch() has no project_id. Use its documented SDK
        # alternative so a visitor's selected project is honored explicitly.
        # Connected Stagehand browsers do not own the provider session; the
        # exit stack releases it and deletes our uploaded extension separately.
        provider = await cleanup.enter_async_context(AsyncBrowserbase(
            api_key=config.api_key, max_retries=0,
        ))
        archive = await asyncio.to_thread(build_extension_archive)
        extension = await provider.extensions.create(file=("stagehand-extension.zip", archive))
        if not extension.id:
            raise RuntimeError("Browserbase returned an invalid extension ID.")
        cleanup.push_async_callback(
            provider.extensions.delete, extension.id,
            extra_headers={"Content-Type": omit},
        )
        session = await provider.sessions.create(
            project_id=config.project_id, extension_id=extension.id,
            proxies=config.proxies, api_timeout=config.session_timeout,
            browser_settings={
                "context": {"id": context_id, "persist": True},
                "solve_captchas": True,
            },
        )
        if not session.id:
            raise RuntimeError("Browserbase returned an invalid session ID.")
        cleanup.push_async_callback(
            provider.sessions.update, session.id,
            project_id=session.project_id, status="REQUEST_RELEASE",
        )
        if session.project_id != config.project_id:
            raise RuntimeError("Browserbase returned a session outside the selected project.")
        browser = await browserbase.connect(api_key=config.api_key, session_id=session.id)
        cleanup.push_async_callback(browser.close)
        # The SDK may invoke callbacks from its own long-lived dispatch task.
        # Bind the session's owner explicitly; never rely on that task's context.
        async def owned_generate(params):
            with model_user_scope(model_user_id):
                return await generate(params)

        agent = await Stagehand.create(
            browser=browser, model=owned_generate,
            logging={"level": "off"},  # Prompts contain applicant personal information.
            telemetry=telemetry,
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
