"""user_settings.stats_digest_enabled; the digest notification kinds (P8.11)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-19

Null means the environment default (`STATS_DIGEST_ENABLED`), like every user setting (ADR 0036).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Downgrade drops the digest bookkeeping rows (a digest may then be sent again).
reversible: bool = True

KINDS_BEFORE = (
    "kind IN ('new_activity', 'checkin_prompt', 'checkin_reminder', 'coach_reminder_before', "
    "'coach_reminder_now', 'coach_nudge_30', 'coach_nudge_90', 'coach_missed', "
    "'coach_workout_start', 'coach_rest_over', 'coach_under_target', 'coach_workout_done')"
)
KINDS_AFTER = KINDS_BEFORE[:-1] + ", 'stats_digest_week', 'stats_digest_month')"


def upgrade() -> None:
    op.add_column("user_settings", sa.Column("stats_digest_enabled", sa.Boolean(), nullable=True))
    op.drop_constraint(op.f("ck_notifications_kind"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_kind"), "notifications", KINDS_AFTER)


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind LIKE 'stats_digest_%'")
    op.drop_constraint(op.f("ck_notifications_kind"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_kind"), "notifications", KINDS_BEFORE)
    op.drop_column("user_settings", "stats_digest_enabled")
