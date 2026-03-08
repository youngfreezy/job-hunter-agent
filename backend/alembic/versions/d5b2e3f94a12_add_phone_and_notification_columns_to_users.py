"""add phone and notification columns to users

Revision ID: d5b2e3f94a12
Revises: c4a1f2e83b01
Create Date: 2026-03-08 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5b2e3f94a12'
down_revision: Union[str, None] = 'c4a1f2e83b01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number TEXT UNIQUE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_channel TEXT DEFAULT 'email'")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS notification_channel")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS phone_verified")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS phone_number")
