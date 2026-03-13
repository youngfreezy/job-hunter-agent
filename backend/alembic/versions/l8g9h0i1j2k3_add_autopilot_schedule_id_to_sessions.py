"""add autopilot_schedule_id to sessions

Revision ID: l8g9h0i1j2k3
Revises: k7f8g9h0i1j2
Create Date: 2026-03-13 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'l8g9h0i1j2k3'
down_revision: Union[str, None] = 'k7f8g9h0i1j2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'sessions',
        sa.Column('autopilot_schedule_id', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('sessions', 'autopilot_schedule_id')
