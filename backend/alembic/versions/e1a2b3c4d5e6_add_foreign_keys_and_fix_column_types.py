"""add foreign keys and fix column types

Revision ID: e1a2b3c4d5e6
Revises: d5b2e3f94a12
Create Date: 2026-03-09 12:00:00.000000

Fixes scalability concerns:
- Converts sessions.user_id and dead_letter_queue.user_id from TEXT to UUID
- Cleans orphaned records that reference non-existent parents
- Adds foreign key constraints with ON DELETE CASCADE
- Adds LISTEN/NOTIFY trigger for autopilot scheduler optimization
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e1a2b3c4d5e6'
down_revision: Union[str, None] = 'd5b2e3f94a12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------------
    # Step 1: Clean orphaned records (before type changes or FK adds)
    # ---------------------------------------------------------------

    # Delete application_results pointing to non-existent sessions
    op.execute("""
        DELETE FROM application_results
        WHERE session_id NOT IN (SELECT id FROM sessions)
    """)

    # Delete dead_letter_queue entries pointing to non-existent sessions
    op.execute("""
        DELETE FROM dead_letter_queue
        WHERE session_id NOT IN (SELECT id FROM sessions)
    """)

    # Delete dead_letter_queue entries with invalid or non-existent user UUIDs
    op.execute("""
        DELETE FROM dead_letter_queue
        WHERE user_id !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
           OR user_id::uuid NOT IN (SELECT id FROM users)
    """)

    # Delete sessions pointing to non-existent users
    op.execute("""
        DELETE FROM sessions
        WHERE user_id !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
           OR user_id::uuid NOT IN (SELECT id FROM users)
    """)

    # Delete autopilot_schedules pointing to non-existent users
    op.execute("""
        DELETE FROM autopilot_schedules
        WHERE user_id NOT IN (SELECT id FROM users)
    """)

    # ---------------------------------------------------------------
    # Step 2: Fix column type mismatches (TEXT → UUID)
    # ---------------------------------------------------------------

    # sessions.user_id: TEXT → UUID
    op.execute("""
        ALTER TABLE sessions
        ALTER COLUMN user_id TYPE UUID USING user_id::uuid
    """)

    # dead_letter_queue.user_id: TEXT → UUID
    op.execute("""
        ALTER TABLE dead_letter_queue
        ALTER COLUMN user_id TYPE UUID USING user_id::uuid
    """)

    # ---------------------------------------------------------------
    # Step 3: Add foreign key constraints (ON DELETE CASCADE)
    # ---------------------------------------------------------------

    # sessions.user_id → users(id)
    op.execute("""
        ALTER TABLE sessions
        ADD CONSTRAINT fk_sessions_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    """)

    # application_results.session_id → sessions(id)
    op.execute("""
        ALTER TABLE application_results
        ADD CONSTRAINT fk_app_results_session
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    """)

    # autopilot_schedules.user_id → users(id)
    op.execute("""
        ALTER TABLE autopilot_schedules
        ADD CONSTRAINT fk_autopilot_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    """)

    # dead_letter_queue.user_id → users(id)
    op.execute("""
        ALTER TABLE dead_letter_queue
        ADD CONSTRAINT fk_dlq_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    """)

    # dead_letter_queue.session_id → sessions(id)
    op.execute("""
        ALTER TABLE dead_letter_queue
        ADD CONSTRAINT fk_dlq_session
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    """)

    # ---------------------------------------------------------------
    # Step 4: LISTEN/NOTIFY trigger for autopilot scheduler
    # ---------------------------------------------------------------

    op.execute("""
        CREATE OR REPLACE FUNCTION notify_autopilot_change() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('autopilot_schedules_changed', NEW.id::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER autopilot_notify
        AFTER INSERT OR UPDATE ON autopilot_schedules
        FOR EACH ROW EXECUTE FUNCTION notify_autopilot_change()
    """)


def downgrade() -> None:
    # Remove trigger and function
    op.execute("DROP TRIGGER IF EXISTS autopilot_notify ON autopilot_schedules")
    op.execute("DROP FUNCTION IF EXISTS notify_autopilot_change()")

    # Drop foreign keys
    op.execute("ALTER TABLE dead_letter_queue DROP CONSTRAINT IF EXISTS fk_dlq_session")
    op.execute("ALTER TABLE dead_letter_queue DROP CONSTRAINT IF EXISTS fk_dlq_user")
    op.execute("ALTER TABLE autopilot_schedules DROP CONSTRAINT IF EXISTS fk_autopilot_user")
    op.execute("ALTER TABLE application_results DROP CONSTRAINT IF EXISTS fk_app_results_session")
    op.execute("ALTER TABLE sessions DROP CONSTRAINT IF EXISTS fk_sessions_user")

    # Revert UUID columns back to TEXT
    op.execute("ALTER TABLE dead_letter_queue ALTER COLUMN user_id TYPE TEXT USING user_id::text")
    op.execute("ALTER TABLE sessions ALTER COLUMN user_id TYPE TEXT USING user_id::text")
