"""Centralised configuration loaded from environment / .env file."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings

# Resolve project root (.env lives at the repo root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings.

    Values are read from environment variables first, then from a ``.env``
    file in the project root.  Every field that has a default can be omitted
    from the environment; required fields (no default) must be present at
    startup.
    """

    # --- LLM ---
    LLM_PROVIDER: str = "openai"  # "openai" or "anthropic"
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_DEFAULT_MODEL: str = "gpt-5-mini"
    OPENAI_PREMIUM_MODEL: str = "gpt-5"
    OPENAI_BROWSER_MODEL: str = "gpt-5-mini"
    ANTHROPIC_DEFAULT_MODEL: str = "claude-sonnet-4-6"
    ANTHROPIC_PREMIUM_MODEL: str = "claude-opus-4-6"
    ANTHROPIC_LIGHT_MODEL: str = "claude-haiku-4-5-20251001"
    ANTHROPIC_BROWSER_MODEL: str = "claude-sonnet-4-5"

    # --- Postgres ---
    DATABASE_URL: str = (
        "postgresql://jobhunter:jobhunter_dev@localhost:5433/jobhunter"
    )

    # --- Neo4j (optional – used for validation-rule storage) ---
    NEO4J_URI: Optional[str] = None
    NEO4J_USER: Optional[str] = None
    NEO4J_PASSWORD: Optional[str] = None

    # --- Redis ---
    REDIS_URL: str = "redis://:jobhunter_redis_dev@localhost:6379"

    # --- Auth ---
    NEXTAUTH_SECRET: Optional[str] = None

    # --- Stripe ---
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None

    # --- Email ---
    RESEND_API_KEY: Optional[str] = None

    # --- LangSmith ---
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: str = "job-hunter-agent"

    # --- Observability ---
    SENTRY_DSN: Optional[str] = None
    LOG_LEVEL: str = "INFO"

    # --- Browser ---
    PROXY_URL: Optional[str] = None
    BROWSER_HEADLESS: bool = False
    BROWSER_SLOW_MO: int = 0  # ms delay between Playwright actions (smoother in headed mode)
    BROWSER_MODE: str = "cdp"  # "cdp" (real Chrome) or "patchright" (built-in Chromium)
    BROWSER_PROVIDER: str = "local"  # "local" or "brightdata"
    BRIGHT_DATA_BROWSER_ENABLED: bool = False
    BRIGHT_DATA_BROWSER_CDP_URL: Optional[str] = None
    BRIGHT_DATA_BROWSER_USERNAME: Optional[str] = None
    BRIGHT_DATA_BROWSER_PASSWORD: Optional[str] = None
    BRIGHT_DATA_BROWSER_HOST: str = "brd.superproxy.io"
    BRIGHT_DATA_BROWSER_PORT: int = 9222
    BRIGHT_DATA_BROWSER_TIMEOUT_MS: int = 45000
    BRIGHT_DATA_BROWSER_FORCE: bool = False
    BRIGHT_DATA_BROWSER_USE_FOR_DISCOVERY: bool = False
    BRIGHT_DATA_BROWSER_BOARDS: str = "linkedin,indeed,glassdoor"

    # --- Bright Data Datasets API (for discovery) ---
    BRIGHT_DATA_API_TOKEN: Optional[str] = None
    BRIGHT_DATA_DISCOVERY_ENABLED: bool = False

    model_config = {
        "env_file": (
            str(_PROJECT_ROOT / ".env"),
            str(_PROJECT_ROOT / ".env.local"),
        ),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# ---------------------------------------------------------------------------
# Pipeline constants
# ---------------------------------------------------------------------------
MAX_APPLICATION_JOBS = 20  # Max jobs shown/approved/tailored per session

# Singleton – import this everywhere instead of re-instantiating.
settings = Settings()  # type: ignore[call-arg]


def get_settings() -> Settings:
    """Return the module-level Settings singleton.

    Provided as a convenience so agents can call ``get_settings()`` without
    importing the bare ``settings`` object directly.
    """
    return settings
