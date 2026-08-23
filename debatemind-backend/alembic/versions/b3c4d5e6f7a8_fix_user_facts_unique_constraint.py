"""fix missing unique constraint on user_facts(user_id, fact_text)

The a2b3c4d5e6f7 migration declares this constraint, but the live table never
got it — record_user_facts()'s ON CONFLICT (user_id, fact_text) DO NOTHING has
been failing on every call as a result (InvalidColumnReferenceError: no unique
or exclusion constraint matching the ON CONFLICT specification), silently
swallowed by pipeline.py, so no personal fact has ever actually been saved.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-07-03 19:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # On a fresh database, a2b3c4d5e6f7 already creates this constraint inline
    # via create_table(); this migration only needs to add it on deployments
    # where that constraint failed to apply the first time around.
    inspector = sa.inspect(op.get_bind())
    existing = {uc["name"] for uc in inspector.get_unique_constraints("user_facts")}
    if "uq_user_facts_user_id_fact_text" not in existing:
        op.create_unique_constraint(
            "uq_user_facts_user_id_fact_text", "user_facts", ["user_id", "fact_text"]
        )


def downgrade() -> None:
    # On a fresh database this constraint was created inline by a2b3c4d5e6f7,
    # not by this migration's upgrade() — dropping it here would strip a
    # predecessor-owned constraint and revert record_user_facts()'s ON CONFLICT
    # to the broken state this migration exists to fix. No-op is intentional.
    pass
