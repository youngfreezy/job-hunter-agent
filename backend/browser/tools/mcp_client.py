# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Bright Data MCP client -- async context manager for MCP tool calls.

Manages the npx mcp-remote subprocess lifecycle and provides
helper methods for search_engine and scrape_as_markdown tools.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

_MCP_BASE_URL = "https://mcp.brightdata.com/mcp"


def _get_mcp_url() -> str:
    token = get_settings().BRIGHT_DATA_MCP_TOKEN
    if not token:
        raise RuntimeError(
            "BRIGHT_DATA_MCP_TOKEN not set. Get it from "
            "brightdata.com > Settings > API tokens."
        )
    return f"{_MCP_BASE_URL}?token={token}"


@asynccontextmanager
async def mcp_session() -> AsyncGenerator[ClientSession, None]:
    """Start Bright Data MCP subprocess and yield a ClientSession.

    Usage::

        async with mcp_session() as session:
            result = await session.call_tool("search_engine", {"query": "..."})
    """
    server_params = StdioServerParameters(
        command="npx",
        args=["mcp-remote", _get_mcp_url()],
    )

    logger.info("Starting Bright Data MCP subprocess...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            logger.info("Bright Data MCP session initialized")
            yield session
    logger.info("Bright Data MCP subprocess stopped")


async def mcp_search(session: ClientSession, query: str) -> str:
    """Call search_engine and return the text result."""
    result = await session.call_tool("search_engine", arguments={"query": query})
    text = ""
    for block in result.content:
        if hasattr(block, "text"):
            text += block.text
    return text


async def mcp_scrape(session: ClientSession, url: str) -> str:
    """Call scrape_as_markdown and return the text result."""
    result = await session.call_tool("scrape_as_markdown", arguments={"url": url})
    text = ""
    for block in result.content:
        if hasattr(block, "text"):
            text += block.text
    return text
