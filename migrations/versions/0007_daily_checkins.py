"""daily check-ins; check-in prompt and reminder notification kinds

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Rollback (ADR 0026): downgrade() restores the previous revision's schema; it drops only what
# this revision added.
reversible: bool = True

KINDS_BEFORE = "kind IN ('new_activity')"
KINDS_AFTER = "kind IN ('new_activity', 'checkin_prompt', 'checkin_reminder')"


def upgrade() -> None:
    op.create_table(
        "daily_checkins",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("workout_id", sa.BigInteger(), nullable=True),
        sa.Column("reason_note", sa.Text(), nullable=True),
        sa.Column("sleep_hours", sa.Numeric(3, 1), nullable=True),
        sa.Column("energy_1_5", sa.Integer(), nullable=True),
        sa.Column("body_weight_kg", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('done', 'partial', 'skipped', 'rest', 'sick_or_injured')",
            name=op.f("ck_daily_checkins_status"),
        ),
        sa.CheckConstraint(
            "sleep_hours IS NULL OR sleep_hours BETWEEN 0 AND 24",
            name=op.f("ck_daily_checkins_sleep_hours"),
        ),
        sa.CheckConstraint(
            "energy_1_5 IS NULL OR energy_1_5 BETWEEN 1 AND 5",
            name=op.f("ck_daily_checkins_energy_1_5"),
        ),
        sa.CheckConstraint(
            "body_weight_kg IS NULL OR (body_weight_kg > 0 AND body_weight_kg < 500)",
            name=op.f("ck_daily_checkins_body_weight_kg"),
        ),
        sa.ForeignKeyConstraint(
            ["workout_id"],
            ["workouts.id"],
            name=op.f("fk_daily_checkins_workout_id_workouts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_checkins")),
        sa.UniqueConstraint("date", name=op.f("uq_daily_checkins_date")),
    )
    # New notification kinds (ADR 0001: string enums are CHECK constraints).
    op.drop_constraint(op.f("ck_notifications_kind"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_kind"), "notifications", KINDS_AFTER)


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind IN ('checkin_prompt', 'checkin_reminder')")
    op.drop_constraint(op.f("ck_notifications_kind"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_kind"), "notifications", KINDS_BEFORE)
    op.drop_table("daily_checkins")
