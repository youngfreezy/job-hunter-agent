"""create agent marketplace tables

Revision ID: i5d6e7f8g9h0
Revises: h4c5d6e7f8g9
Create Date: 2026-03-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i5d6e7f8g9h0'
down_revision: Union[str, None] = 'h4c5d6e7f8g9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- agents ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            long_description TEXT,
            icon TEXT DEFAULT 'bot',
            category TEXT NOT NULL,
            credit_cost DECIMAL(10,2) DEFAULT 1.0,
            is_builtin BOOLEAN DEFAULT TRUE,
            is_published BOOLEAN DEFAULT TRUE,
            author_user_id UUID REFERENCES users(id),
            graph_key TEXT,
            route_prefix TEXT,
            frontend_path TEXT,
            input_schema JSONB,
            stages JSONB,
            total_uses INTEGER DEFAULT 0,
            avg_rating DECIMAL(3,2) DEFAULT 0.00,
            rating_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # --- agent_reviews ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_reviews (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id UUID REFERENCES agents(id) ON DELETE CASCADE NOT NULL,
            user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
            session_id TEXT,
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            review_text TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(agent_id, user_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_reviews_agent ON agent_reviews(agent_id)")

    # --- agent_usage ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_usage (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id UUID REFERENCES agents(id) ON DELETE CASCADE NOT NULL,
            user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
            session_id TEXT,
            status TEXT DEFAULT 'started',
            started_at TIMESTAMPTZ DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_usage_agent ON agent_usage(agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_usage_user ON agent_usage(user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_usage")
    op.execute("DROP TABLE IF EXISTS agent_reviews")
    op.execute("DROP TABLE IF EXISTS agents")
