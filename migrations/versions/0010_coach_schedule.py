"""coach (P6.11): program day weekday and start time; coach notification kinds

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Rollback (ADR 0026): downgrade() drops the two columns and the coach notification rows and
# kinds this revision added; nothing older is touched.
reversible: bool = True

KINDS_BEFORE = "kind IN ('new_activity', 'checkin_prompt', 'checkin_reminder')"
KINDS_AFTER = (
    "kind IN ('new_activity', 'checkin_prompt', 'checkin_reminder', 'coach_reminder_before', "
    "'coach_reminder_now', 'coach_nudge_30', 'coach_nudge_90', 'coach_missed', "
    "'coach_workout_start', 'coach_rest_over', 'coach_under_target', 'coach_workout_done')"
)


def upgrade() -> None:
    op.add_column("program_days", sa.Column("weekday", sa.Integer(), nullable=True))
    op.add_column("program_days", sa.Column("start_time", sa.Time(), nullable=True))
    op.create_check_constraint(
        op.f("ck_program_days_weekday"),
        "program_days",
        "weekday IS NULL OR weekday BETWEEN 0 AND 6",
    )
    op.drop_constraint(op.f("ck_notifications_kind"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_kind"), "notifications", KINDS_AFTER)


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind LIKE 'coach_%'")
    op.drop_constraint(op.f("ck_notifications_kind"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_kind"), "notifications", KINDS_BEFORE)
    op.drop_constraint(op.f("ck_program_days_weekday"), "program_days", type_="check")
    op.drop_column("program_days", "start_time")
    op.drop_column("program_days", "weekday")
