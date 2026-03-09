"""add user_id to application_results for per-user dedup

Revision ID: f2a3b4c5d6e7
Revises: e1a2b3c4d5e6
Create Date: 2026-03-09 14:00:00.000000

Adds user_id column to application_results so duplicate checks and
company rate limits are per-user instead of global.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Add user_id column (nullable for existing rows)
    op.execute("""
        ALTER TABLE application_results
        ADD COLUMN IF NOT EXISTS user_id UUID
    """)

    # Step 2: Backfill user_id from sessions table
    op.execute("""
        UPDATE application_results ar
        SET user_id = s.user_id
        FROM sessions s
        WHERE ar.session_id = s.id
          AND ar.user_id IS NULL
    """)

    # Step 3: Partial unique index — one submitted application per user per job
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_app_results_user_job_unique
        ON application_results (user_id, job_id)
        WHERE status = 'submitted'
    """)

    # Step 4: Index for per-user company rate limiting
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_app_results_user_company
        ON application_results (user_id, job_company, created_at)
        WHERE status = 'submitted'
    """)

    # Step 5: FK to users table (nullable, so no constraint — old rows may have NULL)
    # We don't add a NOT NULL constraint since historical rows without sessions
    # would have NULL user_id after backfill.


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_app_results_user_company")
    op.execute("DROP INDEX IF EXISTS idx_app_results_user_job_unique")
    op.execute("ALTER TABLE application_results DROP COLUMN IF EXISTS user_id")
