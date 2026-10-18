"""food_logs: snapshot the food's kcal and macros per 100 g at log time

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-18

Existing entries are backfilled from the food's current values: the best that can be known now.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Rollback (ADR 0026): downgrade() restores the previous revision's schema; it drops only what
# this revision added.
reversible: bool = True


def upgrade() -> None:
    op.add_column("food_logs", sa.Column("kcal_100g", sa.Numeric(6, 1), nullable=True))
    op.add_column("food_logs", sa.Column("protein_100g", sa.Numeric(5, 1), nullable=True))
    op.add_column("food_logs", sa.Column("carbs_100g", sa.Numeric(5, 1), nullable=True))
    op.add_column("food_logs", sa.Column("fat_100g", sa.Numeric(5, 1), nullable=True))
    op.execute(
        "UPDATE food_logs SET kcal_100g = foods.kcal_100g, protein_100g = foods.protein_100g,"
        " carbs_100g = foods.carbs_100g, fat_100g = foods.fat_100g"
        " FROM foods WHERE foods.id = food_logs.food_id"
    )
    op.alter_column("food_logs", "kcal_100g", nullable=False)


def downgrade() -> None:
    op.drop_column("food_logs", "fat_100g")
    op.drop_column("food_logs", "carbs_100g")
    op.drop_column("food_logs", "protein_100g")
    op.drop_column("food_logs", "kcal_100g")
