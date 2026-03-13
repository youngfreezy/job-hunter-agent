"""add unique index on task_id to skyvern_task_artifacts

Revision ID: m9h0i1j2k3l4
Revises: l8g9h0i1j2k3
Create Date: 2026-03-13 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'm9h0i1j2k3l4'
down_revision: Union[str, None] = 'l8g9h0i1j2k3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_skyvern_artifacts_task_id',
        'skyvern_task_artifacts',
        ['task_id'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_skyvern_artifacts_task_id', 'skyvern_task_artifacts')
