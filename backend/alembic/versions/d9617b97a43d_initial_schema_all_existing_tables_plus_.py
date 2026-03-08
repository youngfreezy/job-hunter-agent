"""initial schema — all existing tables plus sessions table

Revision ID: d9617b97a43d
Revises:
Create Date: 2026-03-07 20:04:03.106590

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9617b97a43d'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT UNIQUE NOT NULL,
            wallet_balance DECIMAL(10,2) DEFAULT 0.00,
            free_applications_remaining INT DEFAULT 3,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # --- wallet_transactions ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id),
            amount DECIMAL(10,2) NOT NULL,
            balance_after DECIMAL(10,2) NOT NULL,
            type TEXT NOT NULL,
            reference_id TEXT,
            description TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_wallet_tx_user ON wallet_transactions(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_wallet_tx_created ON wallet_transactions(user_id, created_at DESC)")

    # --- application_results ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS application_results (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            status TEXT NOT NULL,
            job_title TEXT,
            job_company TEXT,
            job_url TEXT,
            job_board TEXT,
            job_location TEXT,
            error_message TEXT,
            cover_letter TEXT,
            tailored_resume_text TEXT,
            duration_seconds INT,
            screenshot_path TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_app_results_session ON application_results(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_app_results_session_status ON application_results(session_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_app_results_job_id_status ON application_results(job_id, status)")

    # --- board_selectors ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS board_selectors (
            id SERIAL PRIMARY KEY,
            board TEXT NOT NULL,
            selector TEXT NOT NULL,
            success_count INT NOT NULL DEFAULT 1,
            fail_count INT NOT NULL DEFAULT 0,
            last_used TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_checked TIMESTAMPTZ,
            last_check_passed BOOLEAN,
            UNIQUE (board, selector)
        )
    """)

    # --- apply_selectors ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS apply_selectors (
            id SERIAL PRIMARY KEY,
            platform TEXT NOT NULL,
            step_type TEXT NOT NULL,
            selector TEXT NOT NULL,
            success_count INT NOT NULL DEFAULT 1,
            fail_count INT NOT NULL DEFAULT 0,
            last_used TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_checked TIMESTAMPTZ,
            last_check_passed BOOLEAN,
            UNIQUE (platform, step_type, selector)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_apply_selectors_platform_step ON apply_selectors (platform, step_type)")

    # --- sessions (NEW — persists session metadata to survive restarts) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'intake',
            keywords JSONB DEFAULT '[]',
            locations JSONB DEFAULT '[]',
            remote_only BOOLEAN DEFAULT FALSE,
            salary_min INT,
            resume_text_snippet TEXT,
            linkedin_url TEXT,
            applications_submitted INT DEFAULT 0,
            applications_failed INT DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at DESC)")

    # --- dead_letter_queue (NEW — captures failed applications for retry) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS dead_letter_queue (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            job_title TEXT,
            job_company TEXT,
            job_url TEXT,
            job_board TEXT,
            error_message TEXT,
            error_type TEXT,
            attempt_count INT DEFAULT 1,
            status TEXT DEFAULT 'pending',
            payload JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            retry_after TIMESTAMPTZ,
            resolved_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_dlq_status ON dead_letter_queue(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_dlq_user ON dead_letter_queue(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_dlq_session ON dead_letter_queue(session_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dead_letter_queue")
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS apply_selectors")
    op.execute("DROP TABLE IF EXISTS board_selectors")
    op.execute("DROP TABLE IF EXISTS application_results")
    op.execute("DROP TABLE IF EXISTS wallet_transactions")
    op.execute("DROP TABLE IF EXISTS users")
