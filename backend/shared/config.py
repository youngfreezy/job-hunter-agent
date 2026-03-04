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
    ANTHROPIC_API_KEY: str

    # --- Postgres ---
    DATABASE_URL: str = (
        "postgresql://jobhunter:jobhunter_dev@localhost:5433/jobhunter"
    )

    # --- Neo4j (optional – used for validation-rule storage) ---
    NEO4J_URI: Optional[str] = None
    NEO4J_USER: Optional[str] = None
    NEO4J_PASSWORD: Optional[str] = None

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379"

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

    # --- Browser proxy (anti-detection) ---
    PROXY_URL: Optional[str] = None

    # --- Feature flags ---
    SIMULATE_DISCOVERY: bool = False  # True = use Claude-generated mock listings
    SIMULATE_APPLICATIONS: bool = False  # True = skip real Playwright form filling

    model_config = {
        "env_file": str(_PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton – import this everywhere instead of re-instantiating.
settings = Settings()  # type: ignore[call-arg]


def get_settings() -> Settings:
    """Return the module-level Settings singleton.

    Provided as a convenience so agents can call ``get_settings()`` without
    importing the bare ``settings`` object directly.
    """
    return settings
