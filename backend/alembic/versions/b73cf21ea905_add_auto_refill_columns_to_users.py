"""add auto_refill columns to users

Revision ID: b73cf21ea905
Revises: a51bd84bbfa3
Create Date: 2026-03-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b73cf21ea905'
down_revision: Union[str, None] = 'a51bd84bbfa3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_refill_enabled BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_refill_threshold DECIMAL(10,2) DEFAULT 5.0")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_refill_pack_id TEXT DEFAULT 'top_up_10'")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS auto_refill_enabled")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS auto_refill_threshold")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS auto_refill_pack_id")
