# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Shared LLM utilities with provider-aware model construction and retries."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic
from backend.shared.anthropic_compat import CompatibleChatAnthropic, LATEST_MODELS, model_options
from langchain_openai import ChatOpenAI

from backend.shared.config import get_settings
from backend.shared.model_access import current_model_credentials, model_provider_for_context

logger = logging.getLogger(__name__)

# Retry config
MAX_RETRIES = 5
INITIAL_BACKOFF = 10
MAX_BACKOFF = 60


def get_llm_provider() -> str:
    """Return the configured LLM provider."""
    settings = get_settings()
    provider = model_provider_for_context()
    if provider not in {"openai", "anthropic"}:
        raise ValueError(f"Unsupported LLM_PROVIDER={settings.LLM_PROVIDER!r}")
    return provider



def anthropic_default_headers() -> dict[str, str]:
    """Headers every Anthropic request needs.

    An organization-scoped API key must name the workspace it bills to, or the
    API answers 400 asking for ``anthropic-workspace-id``.
    """
    credentials = current_model_credentials()
    if credentials.workspace_id:
        return {"anthropic-workspace-id": credentials.workspace_id}
    return {}

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
    credentials = current_model_credentials()
    provider = credentials.provider
    resolved_model = model or default_model()
    if not credentials.server_funded and not resolved_model.startswith("claude-"):
        resolved_model = default_model()

    from backend.shared.model_budget import configured_ledger, BudgetChatAnthropic, BudgetStopped, Ledger, MODEL
    budget_path = configured_ledger()
    if budget_path and credentials.server_funded:
        if provider != 'anthropic' or not credentials.api_key:
            raise BudgetStopped('Budget mode requires the approved Anthropic provider.')
        Ledger(budget_path).snapshot()  # Missing/corrupt ledgers must never silently reset.
        return BudgetChatAnthropic(
            model=MODEL, api_key=credentials.api_key,
            anthropic_api_url='https://api.anthropic.com',
            max_tokens=max_tokens, **model_options(MODEL, temperature), max_retries=0,
            disable_streaming=True, timeout=timeout or 90,
            default_headers=anthropic_default_headers() or None,
            budget_ledger_path=budget_path,
        )

    if provider == "openai":
        if not credentials.api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "api_key": credentials.api_key,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
            "max_retries": MAX_RETRIES,
        }
        if resolved_model.startswith(('gpt-6-', 'gpt-6.')):
            # GPT-6 tool workflows use Responses; Astra/Sol reject effort none.
            kwargs.pop('temperature', None)
            kwargs.update(use_responses_api=True, reasoning_effort='low')
        if timeout:
            kwargs["timeout"] = timeout
        return ChatOpenAI(**kwargs)

    if not credentials.api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
    kwargs = {
        "model": resolved_model,
        "api_key": credentials.api_key,
        "max_tokens": max_tokens,
        **model_options(resolved_model, temperature),
        "max_retries": MAX_RETRIES,
    }
    if timeout:
        kwargs["timeout"] = timeout
    headers = anthropic_default_headers()
    if headers:
        kwargs["default_headers"] = headers
    client_class = CompatibleChatAnthropic if resolved_model in LATEST_MODELS else ChatAnthropic
    return client_class(**kwargs)


def build_browser_use_llm(
    *,
    model: Optional[str] = None,
    max_tokens: int = 8192,
    temperature: float = 0.0,
) -> Any:
    """Build a browser-use-compatible LLM instance for the configured provider."""
    from backend.shared.model_budget import configured_ledger, BudgetStopped
    credentials = current_model_credentials()
    if configured_ledger() and credentials.server_funded:
        raise BudgetStopped('Alternate browser-use provider is disabled in budget mode; use Stagehand.')
    settings = get_settings()
    provider = credentials.provider
    resolved_model = model or browser_model()

    if provider == "openai":
        if not credentials.api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")

        browser_options = {'temperature': temperature}
        if resolved_model.startswith(('gpt-6-', 'gpt-6.')):
            if resolved_model != 'gpt-6-luna':
                raise ValueError('Use Stagehand for GPT-6 models requiring the Responses API.')
            # This browser-use version supports Chat Completions only. Luna
            # supports tools there with effort none; register its new model ID.
            browser_options = {'temperature': None, 'frequency_penalty': None,
                               'reasoning_effort': 'none', 'reasoning_models': [resolved_model]}
        from backend.shared.optional_browser import require_browser_use
        BrowserUseChatOpenAI = require_browser_use().ChatOpenAI
        return BrowserUseChatOpenAI(
            model=resolved_model,
            api_key=credentials.api_key,
            max_completion_tokens=max_tokens,
            max_retries=MAX_RETRIES,
            **browser_options,
        )

    if not credentials.api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
    if resolved_model in LATEST_MODELS:
        raise ValueError('Use Stagehand for Claude 5.5; this browser-use adapter forces tool calls.')
    from backend.shared.optional_browser import require_browser_use
    BrowserUseChatAnthropic = require_browser_use().ChatAnthropic

    bu_kwargs: dict[str, Any] = {
        "model": resolved_model,
        "api_key": credentials.api_key,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = anthropic_default_headers()
    if headers:
        bu_kwargs["default_headers"] = headers
    return BrowserUseChatAnthropic(**bu_kwargs)


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
