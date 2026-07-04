"""add logic/evidence/rhetoric scores to voice_sessions

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-07-04 01:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("voice_sessions", sa.Column("score_logic", sa.Float(), nullable=True))
    op.add_column("voice_sessions", sa.Column("score_evidence", sa.Float(), nullable=True))
    op.add_column("voice_sessions", sa.Column("score_rhetoric", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("voice_sessions", "score_rhetoric")
    op.drop_column("voice_sessions", "score_evidence")
    op.drop_column("voice_sessions", "score_logic")
