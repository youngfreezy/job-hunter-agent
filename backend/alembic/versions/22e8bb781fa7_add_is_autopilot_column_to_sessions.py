"""Add is_autopilot column to sessions

Revision ID: 22e8bb781fa7
Revises: m9h0i1j2k3l4
Create Date: 2026-03-14 10:14:10.251539

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '22e8bb781fa7'
down_revision: Union[str, None] = 'm9h0i1j2k3l4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('is_autopilot', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('sessions', 'is_autopilot')
