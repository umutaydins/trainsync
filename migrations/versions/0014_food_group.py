"""foods and food_logs: food_group, so only free sugar counts toward the daily limit (ADR 0032)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Rollback (ADR 0026): downgrade() drops the column; groups stored since are lost (Open Food
# Facts fills them again for cached products on the next lookup).
reversible: bool = True

GROUPS = ("sweets", "dessert", "sugary_drink", "fruit", "vegetable", "plain_dairy", "other")


def upgrade() -> None:
    for table in ("foods", "food_logs"):
        op.add_column(table, sa.Column("food_group", sa.String(16), nullable=True))
    values = ", ".join(f"'{group}'" for group in GROUPS)
    op.create_check_constraint(op.f("ck_foods_food_group"), "foods", f"food_group IN ({values})")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_foods_food_group"), "foods", type_="check")
    for table in ("food_logs", "foods"):
        op.drop_column(table, "food_group")
