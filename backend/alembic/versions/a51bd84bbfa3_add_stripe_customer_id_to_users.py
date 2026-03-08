"""add stripe_customer_id to users

Revision ID: a51bd84bbfa3
Revises: d9617b97a43d
Create Date: 2026-03-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a51bd84bbfa3'
down_revision: Union[str, None] = 'd9617b97a43d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT UNIQUE")


def downgrade() -> None:
    op.drop_column('users', 'stripe_customer_id')
