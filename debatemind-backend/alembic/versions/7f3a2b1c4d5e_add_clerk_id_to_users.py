"""add clerk_id to users

Revision ID: 7f3a2b1c4d5e
Revises: a1b2c3d4e5f6
Create Date: 2026-07-02 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "7f3a2b1c4d5e"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("clerk_id", sa.String(), nullable=True))
    op.create_index(op.f("ix_users_clerk_id"), "users", ["clerk_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_clerk_id"), table_name="users")
    op.drop_column("users", "clerk_id")
