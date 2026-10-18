"""workouts.client_id: client-generated id that makes starting a workout idempotent (ADR 0017)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-18

Existing workouts get a random id; only new starts carry a client's id.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Rollback (ADR 0026): downgrade() restores the previous revision's schema; it drops only what
# this revision added.
reversible: bool = True


def upgrade() -> None:
    op.add_column("workouts", sa.Column("client_id", sa.UUID(), nullable=True))
    op.execute("UPDATE workouts SET client_id = gen_random_uuid()")
    op.alter_column("workouts", "client_id", nullable=False)
    op.create_unique_constraint(op.f("uq_workouts_client_id"), "workouts", ["client_id"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_workouts_client_id"), "workouts", type_="unique")
    op.drop_column("workouts", "client_id")
