"""add unique index on task_id to skyvern_task_artifacts

Revision ID: m9h0i1j2k3l4
Revises: l8g9h0i1j2k3
Create Date: 2026-03-13 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'm9h0i1j2k3l4'
down_revision: Union[str, None] = 'l8g9h0i1j2k3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirrors backend/shared/screenshot_store.py, which creates this table at app
# start.  On a fresh database (CI, a new deployment) the migration chain runs
# before the app ever starts, so the table has to exist before the constraint
# can be added.
_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS skyvern_task_artifacts (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    skyvern_status TEXT NOT NULL,
    failure_reason TEXT,
    extracted_information JSONB,
    screenshot_url TEXT,
    action_screenshot_urls JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
)
"""


def upgrade() -> None:
    op.execute(_CREATE_TABLE)
    bind = op.get_bind()
    existing = {
        row[0]
        for row in bind.execute(sa.text(
            "SELECT conname FROM pg_constraint WHERE conname = 'uq_skyvern_artifacts_task_id'"
        ))
    }
    if 'uq_skyvern_artifacts_task_id' not in existing:
        op.create_unique_constraint(
            'uq_skyvern_artifacts_task_id',
            'skyvern_task_artifacts',
            ['task_id'],
        )


def downgrade() -> None:
    op.drop_constraint('uq_skyvern_artifacts_task_id', 'skyvern_task_artifacts')
