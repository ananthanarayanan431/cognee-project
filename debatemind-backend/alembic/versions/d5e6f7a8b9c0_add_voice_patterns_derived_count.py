"""add patterns_derived_count watermark to voice_sessions

Tracks how many of a voice session's user turns have already been classified
into Cognitive Fingerprint patterns, so the live per-turn derivation and the
end-of-session sweep don't double-count the same turn.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-04 08:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "voice_sessions",
        sa.Column(
            "patterns_derived_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("voice_sessions", "patterns_derived_count")
