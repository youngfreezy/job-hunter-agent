"""create autopilot_schedules table

Revision ID: c4a1f2e83b01
Revises: b73cf21ea905
Create Date: 2026-03-08 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = 'c4a1f2e83b01'
down_revision: Union[str, None] = 'b73cf21ea905'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'autopilot_schedules',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.Text(), nullable=False, server_default='My Job Search'),
        sa.Column('keywords', JSONB, nullable=False, server_default='[]'),
        sa.Column('locations', JSONB, nullable=False, server_default='["Remote"]'),
        sa.Column('remote_only', sa.Boolean(), server_default='false'),
        sa.Column('salary_min', sa.Integer(), nullable=True),
        sa.Column('search_radius', sa.Integer(), server_default='100'),
        sa.Column('resume_text', sa.Text(), nullable=True),
        sa.Column('resume_bytes', sa.LargeBinary(), nullable=True),
        sa.Column('resume_filename', sa.Text(), nullable=True),
        sa.Column('linkedin_url', sa.Text(), nullable=True),
        sa.Column('preferences', JSONB, server_default='{}'),
        sa.Column('session_config', JSONB, nullable=True),
        sa.Column('cron_expression', sa.Text(), nullable=False, server_default='0 8 * * 1-5'),
        sa.Column('timezone', sa.Text(), server_default='America/New_York'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('auto_approve', sa.Boolean(), server_default='false'),
        sa.Column('notification_email', sa.Text(), nullable=True),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_session_id', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_autopilot_user', 'autopilot_schedules', ['user_id'])
    op.create_index(
        'idx_autopilot_next_run',
        'autopilot_schedules',
        ['next_run_at'],
        postgresql_where=sa.text('is_active = TRUE'),
    )


def downgrade() -> None:
    op.drop_index('idx_autopilot_next_run', table_name='autopilot_schedules')
    op.drop_index('idx_autopilot_user', table_name='autopilot_schedules')
    op.drop_table('autopilot_schedules')
