#!/usr/bin/env python3
# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Standalone test for Bright Data MCP connectivity.

Verifies that we can:
1. Connect to Bright Data MCP server via npx mcp-remote
2. List available tools
3. Call search_engine with a test query
4. Call scrape_as_markdown on a result URL

Usage:
    python scripts/test_mcp_standalone.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

MCP_TOKEN = "c3e3f18f-f09a-43c4-9730-9f00b0ae0501"
MCP_URL = f"https://mcp.brightdata.com/mcp?token={MCP_TOKEN}"


async def main():
    server_params = StdioServerParameters(
        command="npx",
        args=["mcp-remote", MCP_URL],
    )

    print("Connecting to Bright Data MCP server...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Connected!\n")

            # 1. List available tools
            print("=== Available Tools ===")
            tools_result = await session.list_tools()
            for tool in tools_result.tools:
                print(f"  - {tool.name}: {tool.description[:80] if tool.description else 'no description'}")
            print(f"\nTotal: {len(tools_result.tools)} tools\n")

            # 2. Test search_engine
            query = "Senior Software Engineer remote site:boards.greenhouse.io"
            print(f"=== Search: {query} ===")
            search_result = await session.call_tool(
                "search_engine",
                arguments={"query": query},
            )
            # search_result.content is a list of content blocks
            search_text = ""
            for block in search_result.content:
                if hasattr(block, "text"):
                    search_text += block.text
            print(f"Search result ({len(search_text)} chars):")
            print(search_text[:2000])
            print()

            # 3. Extract a URL from search results and scrape it
            # Look for greenhouse.io URLs in the results
            import re
            urls = re.findall(r'https?://[^\s\)\"\']+greenhouse\.io[^\s\)\"\']*', search_text)
            if urls:
                test_url = urls[0]
                print(f"=== Scraping: {test_url[:100]} ===")
                scrape_result = await session.call_tool(
                    "scrape_as_markdown",
                    arguments={"url": test_url},
                )
                scrape_text = ""
                for block in scrape_result.content:
                    if hasattr(block, "text"):
                        scrape_text += block.text
                print(f"Scraped content ({len(scrape_text)} chars):")
                print(scrape_text[:1500])
            else:
                print("No greenhouse.io URLs found in search results to scrape")
                # Try a known URL
                test_url = "https://boards.greenhouse.io/anthropic"
                print(f"=== Scraping known URL: {test_url} ===")
                scrape_result = await session.call_tool(
                    "scrape_as_markdown",
                    arguments={"url": test_url},
                )
                scrape_text = ""
                for block in scrape_result.content:
                    if hasattr(block, "text"):
                        scrape_text += block.text
                print(f"Scraped content ({len(scrape_text)} chars):")
                print(scrape_text[:1500])

            print("\n=== MCP Test Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
