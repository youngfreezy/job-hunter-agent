"""add is_running to autopilot_schedules

Revision ID: k7f8g9h0i1j2
Revises: j6e7f8g9h0i1
Create Date: 2026-03-11 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k7f8g9h0i1j2'
down_revision: Union[str, None] = 'j6e7f8g9h0i1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'autopilot_schedules',
        sa.Column('is_running', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('autopilot_schedules', 'is_running')
