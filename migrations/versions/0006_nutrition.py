"""nutrition: foods (with the Open Food Facts cache), food logs, nutrition profile

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now() -> sa.TextClause:
    return sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "foods",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("barcode", sa.String(length=14), nullable=True),
        sa.Column("kcal_100g", sa.Numeric(6, 1), nullable=False),
        sa.Column("protein_100g", sa.Numeric(5, 1), nullable=True),
        sa.Column("carbs_100g", sa.Numeric(5, 1), nullable=True),
        sa.Column("fat_100g", sa.Numeric(5, 1), nullable=True),
        sa.Column(
            "source", sa.String(length=16), server_default=sa.text("'manual'"), nullable=False
        ),
        sa.Column("favorite", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.CheckConstraint("source IN ('manual', 'openfoodfacts')", name=op.f("ck_foods_source")),
        sa.CheckConstraint("kcal_100g >= 0 AND kcal_100g <= 1000", name=op.f("ck_foods_kcal_100g")),
        sa.CheckConstraint(
            "(protein_100g IS NULL OR protein_100g BETWEEN 0 AND 100)"
            " AND (carbs_100g IS NULL OR carbs_100g BETWEEN 0 AND 100)"
            " AND (fat_100g IS NULL OR fat_100g BETWEEN 0 AND 100)",
            name=op.f("ck_foods_macros_100g"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_foods")),
        sa.UniqueConstraint("barcode", name=op.f("uq_foods_barcode")),
    )
    op.create_table(
        "food_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("meal", sa.String(length=16), nullable=False),
        sa.Column("food_id", sa.BigInteger(), nullable=False),
        sa.Column("grams", sa.Numeric(6, 1), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.CheckConstraint(
            "meal IN ('breakfast', 'lunch', 'dinner', 'snack')", name=op.f("ck_food_logs_meal")
        ),
        sa.CheckConstraint("grams > 0 AND grams <= 5000", name=op.f("ck_food_logs_grams")),
        sa.ForeignKeyConstraint(["food_id"], ["foods.id"], name=op.f("fk_food_logs_food_id_foods")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_logs")),
        sa.UniqueConstraint("client_id", name=op.f("uq_food_logs_client_id")),
    )
    op.create_index("ix_food_logs_date", "food_logs", ["date", "meal"])
    op.create_table(
        "nutrition_profile",
        sa.Column(
            "id", sa.Integer(), server_default=sa.text("1"), autoincrement=False, nullable=False
        ),
        sa.Column("sex", sa.String(length=8), nullable=False),
        sa.Column("birth_year", sa.Integer(), nullable=False),
        sa.Column("height_cm", sa.Numeric(4, 1), nullable=False),
        sa.Column("activity_baseline", sa.String(length=16), nullable=False),
        sa.Column("kcal_target", sa.Integer(), nullable=True),
        sa.Column("protein_target_g", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_nutrition_profile_single_row")),
        sa.CheckConstraint("sex IN ('male', 'female')", name=op.f("ck_nutrition_profile_sex")),
        sa.CheckConstraint(
            "activity_baseline IN ('sedentary', 'light', 'moderate')",
            name=op.f("ck_nutrition_profile_activity_baseline"),
        ),
        sa.CheckConstraint(
            "birth_year BETWEEN 1900 AND 2100", name=op.f("ck_nutrition_profile_birth_year")
        ),
        sa.CheckConstraint(
            "height_cm BETWEEN 100 AND 250", name=op.f("ck_nutrition_profile_height_cm")
        ),
        sa.CheckConstraint(
            "kcal_target IS NULL OR kcal_target > 0", name=op.f("ck_nutrition_profile_kcal_target")
        ),
        sa.CheckConstraint(
            "protein_target_g IS NULL OR protein_target_g >= 0",
            name=op.f("ck_nutrition_profile_protein_target_g"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nutrition_profile")),
    )


def downgrade() -> None:
    op.drop_table("nutrition_profile")
    op.drop_index("ix_food_logs_date", table_name="food_logs")
    op.drop_table("food_logs")
    op.drop_table("foods")
