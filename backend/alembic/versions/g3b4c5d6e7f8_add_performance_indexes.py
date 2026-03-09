"""add performance indexes for sessions, application_results, dead_letter_queue, board_selectors

Revision ID: g3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-03-09 16:00:00.000000

Adds indexes to improve query performance for common access patterns:
- sessions: status + updated_at for interrupted session lookups
- application_results: created_at for data retention cleanup
- dead_letter_queue: partial index on pending items for retry processing
- board_selectors: board column for selector lookups
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'g3b4c5d6e7f8'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_status_updated
        ON sessions (status, updated_at DESC)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_app_results_created
        ON application_results (created_at)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_dlq_status_retry
        ON dead_letter_queue (status, retry_after)
        WHERE status = 'pending'
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_board_selectors_board
        ON board_selectors (board)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_user_created
        ON sessions (user_id, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sessions_user_created")
    op.execute("DROP INDEX IF EXISTS idx_board_selectors_board")
    op.execute("DROP INDEX IF EXISTS idx_dlq_status_retry")
    op.execute("DROP INDEX IF EXISTS idx_app_results_created")
    op.execute("DROP INDEX IF EXISTS idx_sessions_status_updated")
