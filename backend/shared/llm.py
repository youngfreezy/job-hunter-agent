# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Shared LLM utilities with provider-aware model construction and retries."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

# Retry config
MAX_RETRIES = 5
INITIAL_BACKOFF = 10
MAX_BACKOFF = 60


def get_llm_provider() -> str:
    """Return the configured LLM provider."""
    settings = get_settings()
    provider = (settings.LLM_PROVIDER or "openai").strip().lower()
    if provider not in {"openai", "anthropic"}:
        raise ValueError(f"Unsupported LLM_PROVIDER={settings.LLM_PROVIDER!r}")
    return provider


def default_model() -> str:
    settings = get_settings()
    return (
        settings.OPENAI_DEFAULT_MODEL
        if get_llm_provider() == "openai"
        else settings.ANTHROPIC_DEFAULT_MODEL
    )


def premium_model() -> str:
    settings = get_settings()
    return (
        settings.OPENAI_PREMIUM_MODEL
        if get_llm_provider() == "openai"
        else settings.ANTHROPIC_PREMIUM_MODEL
    )


def light_model() -> str:
    settings = get_settings()
    return (
        settings.OPENAI_DEFAULT_MODEL
        if get_llm_provider() == "openai"
        else settings.ANTHROPIC_LIGHT_MODEL
    )


def browser_model() -> str:
    settings = get_settings()
    return (
        settings.OPENAI_BROWSER_MODEL
        if get_llm_provider() == "openai"
        else settings.ANTHROPIC_BROWSER_MODEL
    )


DEFAULT_MODEL = default_model()
PREMIUM_MODEL = premium_model()
HAIKU_MODEL = light_model()
BROWSER_MODEL = browser_model()


def build_llm(
    model: Optional[str] = None,
    *,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    timeout: Optional[int] = None,
) -> Any:
    """Build the configured chat model with shared retry settings."""
    settings = get_settings()
    provider = get_llm_provider()
    resolved_model = model or default_model()

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "api_key": settings.OPENAI_API_KEY,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
            "max_retries": MAX_RETRIES,
        }
        if timeout:
            kwargs["timeout"] = timeout
        return ChatOpenAI(**kwargs)

    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
    kwargs = {
        "model": resolved_model,
        "api_key": settings.ANTHROPIC_API_KEY,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "max_retries": MAX_RETRIES,
    }
    if timeout:
        kwargs["timeout"] = timeout
    return ChatAnthropic(**kwargs)


def build_browser_use_llm(
    *,
    model: Optional[str] = None,
    max_tokens: int = 8192,
    temperature: float = 0.0,
) -> Any:
    """Build a browser-use-compatible LLM instance for the configured provider."""
    settings = get_settings()
    provider = get_llm_provider()
    resolved_model = model or browser_model()

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        from browser_use import ChatOpenAI as BrowserUseChatOpenAI

        return BrowserUseChatOpenAI(
            model=resolved_model,
            api_key=settings.OPENAI_API_KEY,
            max_completion_tokens=max_tokens,
            temperature=temperature,
            max_retries=MAX_RETRIES,
        )

    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
    from browser_use import ChatAnthropic as BrowserUseChatAnthropic

    return BrowserUseChatAnthropic(
        model=resolved_model,
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=max_tokens,
        temperature=temperature,
    )


_RETRYABLE_STATUS_CODES = {"429", "500", "502", "503", "529"}


def _is_retryable(exc: Exception) -> bool:
    """Return True if the exception represents a transient failure worth retrying."""
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, ConnectionError)):
        return True
    err_str = str(exc).lower()
    if "length limit" in err_str or "length_limit" in err_str:
        return False  # Token limit errors won't resolve on retry
    if "rate_limit" in err_str:
        return True
    for code in _RETRYABLE_STATUS_CODES:
        # Match status codes as standalone numbers to avoid false positives
        # (e.g. "500" in "completion_tokens=2500")
        if f" {code}" in err_str or f"({code}" in err_str or f":{code}" in err_str or err_str.startswith(code):
            return True
    return False


async def invoke_with_retry(llm: Any, messages: Any, *, max_retries: int = MAX_RETRIES):
    """Invoke an LLM with manual retry+backoff and circuit breaker protection."""
    from backend.shared.circuit_breaker import llm_breaker, CircuitBreakerOpen

    try:
        async with llm_breaker:
            for attempt in range(max_retries + 1):
                try:
                    return await llm.ainvoke(messages)
                except Exception as exc:
                    if not _is_retryable(exc) or attempt == max_retries:
                        raise
                    wait = min(MAX_BACKOFF, INITIAL_BACKOFF * (2 ** attempt)) + random.uniform(0, 1)
                    logger.warning(
                        "Transient failure (attempt %d/%d), retrying in %.1fs: %s",
                        attempt + 1,
                        max_retries,
                        wait,
                        str(exc)[:120],
                    )
                    await asyncio.sleep(wait)
            raise RuntimeError("Exhausted retries")
    except CircuitBreakerOpen:
        raise  # Let callers handle circuit-open state
