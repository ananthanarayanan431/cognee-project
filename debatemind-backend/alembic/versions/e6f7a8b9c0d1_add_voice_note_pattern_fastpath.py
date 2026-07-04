"""add detected_pattern/outcome to voice_session_notes (fingerprint fast path)

Lets the Cognitive Fingerprint read a voice turn's classified pattern straight
from Postgres (like text reads Exchange.detected_pattern) instead of waiting on
the slow async cognee→Neo4j write, so the graph fills in live during a call.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-07-04 08:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("voice_session_notes", sa.Column("detected_pattern", sa.String(), nullable=True))
    op.add_column("voice_session_notes", sa.Column("outcome", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("voice_session_notes", "outcome")
    op.drop_column("voice_session_notes", "detected_pattern")
