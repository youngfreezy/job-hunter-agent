"""Alembic environment configuration.

Reads DATABASE_URL from the application settings so migrations use the same
connection string as the running app.
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Ensure the backend package is importable (project root = backend's parent)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

config = context.config

# Override sqlalchemy.url from environment / .env if available
try:
    from backend.shared.config import get_settings
    settings = get_settings()
    # Use psycopg (v3) dialect — project uses psycopg, not psycopg2
    url = settings.DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    config.set_main_option("sqlalchemy.url", url)
except Exception:
    pass  # Fall back to alembic.ini value

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
