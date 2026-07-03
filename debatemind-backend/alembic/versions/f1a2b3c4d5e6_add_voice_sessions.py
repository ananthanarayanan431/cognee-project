"""add voice_sessions and voice_session_notes tables

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-07-02 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("debate_session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("openai_session_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("closing_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["debate_session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_voice_sessions_debate_session_id", "voice_sessions", ["debate_session_id"])
    op.create_index("ix_voice_sessions_user_id", "voice_sessions", ["user_id"])

    op.create_table(
        "voice_session_notes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("voice_session_id", sa.String(), nullable=False),
        sa.Column("note_type", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["voice_session_id"], ["voice_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_voice_session_notes_voice_session_id",
        "voice_session_notes",
        ["voice_session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_voice_session_notes_voice_session_id", table_name="voice_session_notes")
    op.drop_table("voice_session_notes")
    op.drop_index("ix_voice_sessions_user_id", table_name="voice_sessions")
    op.drop_index("ix_voice_sessions_debate_session_id", table_name="voice_sessions")
    op.drop_table("voice_sessions")
