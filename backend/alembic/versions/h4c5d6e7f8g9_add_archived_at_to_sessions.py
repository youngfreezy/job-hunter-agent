# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""add archived_at column to sessions for soft-delete/archive support

Revision ID: h4c5d6e7f8g9
Revises: g3b4c5d6e7f8
Create Date: 2026-03-11 03:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'h4c5d6e7f8g9'
down_revision: Union[str, None] = 'g3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ DEFAULT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS archived_at")
