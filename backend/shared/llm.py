"""Shared LLM utilities with built-in rate-limit retry.

Every agent should use ``build_llm()`` instead of constructing
``ChatAnthropic`` directly.  This ensures consistent retry behaviour
across the entire pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from langchain_anthropic import ChatAnthropic

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

# Default models
SONNET_MODEL = "claude-sonnet-4-6"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Retry config
MAX_RETRIES = 5
INITIAL_BACKOFF = 10  # seconds — SDK already retries with short backoffs first
MAX_BACKOFF = 60  # seconds


def build_llm(
    model: str = SONNET_MODEL,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    timeout: Optional[int] = None,
) -> ChatAnthropic:
    """Build a ChatAnthropic instance with retry-friendly settings.

    The Anthropic SDK and LangChain wrapper honour ``max_retries``
    natively — this sets it to a sensible default with exponential
    backoff so 429 rate-limit errors are retried automatically.
    """
    settings = get_settings()
    kwargs: dict = {
        "model": model,
        "api_key": settings.ANTHROPIC_API_KEY,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "max_retries": MAX_RETRIES,
    }
    if timeout:
        kwargs["timeout"] = timeout
    return ChatAnthropic(**kwargs)


async def invoke_with_retry(llm, messages, *, max_retries: int = MAX_RETRIES):
    """Invoke an LLM with manual retry+backoff for rate limits.

    Use this for ``llm.with_structured_output()`` calls or the raw
    Anthropic SDK where the built-in retry may not cover all cases.
    """
    backoff = INITIAL_BACKOFF
    for attempt in range(max_retries + 1):
        try:
            return await llm.ainvoke(messages)
        except Exception as exc:
            err_str = str(exc)
            is_rate_limit = "429" in err_str or "rate_limit" in err_str.lower()
            if not is_rate_limit or attempt == max_retries:
                raise
            wait = min(backoff * (2 ** attempt), MAX_BACKOFF)
            logger.warning(
                "Rate limited (attempt %d/%d), retrying in %.0fs: %s",
                attempt + 1, max_retries, wait, err_str[:120],
            )
            await asyncio.sleep(wait)
    raise RuntimeError("Exhausted retries")  # unreachable
