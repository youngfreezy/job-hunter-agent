"""add application_rules column to users

Revision ID: n1a2b3c4d5e6
Revises: 22e8bb781fa7
Create Date: 2026-10-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'n1a2b3c4d5e6'
down_revision: Union[str, None] = '22e8bb781fa7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Free-text rules the owner writes in Settings; injected into the scoring
    # and form-filling prompts. Empty string means "no rules".
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS application_rules TEXT NOT NULL DEFAULT ''")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS application_rules")
