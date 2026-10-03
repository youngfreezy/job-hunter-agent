"""create browserbase_settings table

Revision ID: o2b3c4d5e6f7
Revises: n1a2b3c4d5e6
Create Date: 2026-10-03 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'o2b3c4d5e6f7'
down_revision: Union[str, None] = 'n1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Per-user Browserbase credentials and persisted-login Context ids.
    # encrypted_api_key is a Fernet token (see backend/shared/browserbase_store.py).
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS browserbase_settings (
            user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            encrypted_api_key TEXT,
            project_id TEXT,
            proxies BOOLEAN NOT NULL DEFAULT FALSE,
            context_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS browserbase_settings")
