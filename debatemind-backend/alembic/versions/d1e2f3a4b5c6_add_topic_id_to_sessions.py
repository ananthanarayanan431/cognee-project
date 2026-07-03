"""add topic_id to sessions

Revision ID: d1e2f3a4b5c6
Revises: a1b2c3d4e5f6
Create Date: 2026-07-02 07:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "7f3a2b1c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("topic_id", sa.String(), nullable=True),
    )
    op.create_index("ix_sessions_topic_id", "sessions", ["topic_id"])


def downgrade() -> None:
    op.drop_index("ix_sessions_topic_id", table_name="sessions")
    op.drop_column("sessions", "topic_id")
