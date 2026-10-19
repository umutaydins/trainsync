"""foods and food_logs: sugars_100g and nova_group (ADR 0032)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Rollback (ADR 0026): downgrade() drops the new columns; sugar and NOVA values stored since are
# lost (they come back from Open Food Facts for cached products on the next lookup only).
reversible: bool = True


def upgrade() -> None:
    for table in ("foods", "food_logs"):
        op.add_column(table, sa.Column("sugars_100g", sa.Numeric(5, 1), nullable=True))
        op.add_column(table, sa.Column("nova_group", sa.SmallInteger(), nullable=True))
    op.create_check_constraint(
        op.f("ck_foods_sugar_nova"),
        "foods",
        "(sugars_100g IS NULL OR sugars_100g BETWEEN 0 AND 100)"
        " AND (nova_group IS NULL OR nova_group BETWEEN 1 AND 4)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_foods_sugar_nova"), "foods", type_="check")
    for table in ("food_logs", "foods"):
        op.drop_column(table, "nova_group")
        op.drop_column(table, "sugars_100g")
