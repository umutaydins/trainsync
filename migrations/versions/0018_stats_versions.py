"""user_data_versions and its triggers; workout_sets (user_id, completed_at) (P8.10, ADR 0038)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-19

Every insert, update and delete on a table the statistics read bumps the user's data version,
which keys the statistics cache. A user gets a version row when the account is created.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
reversible: bool = True

# A copy, not an import: a migration must not change when the application code does.
VERSIONED_TABLES = (
    "activities",
    "workouts",
    "workout_sets",
    "exercises",
    "programs",
    "program_days",
    "program_exercises",
    "food_logs",
    "nutrition_profile",
    "body_metrics",
    "daily_checkins",
)
BUMP = "bump_user_data_version"
CREATE_ROW = "create_user_data_version"


def upgrade() -> None:
    op.create_table(
        "user_data_versions",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_data_versions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_data_versions")),
    )
    op.execute("INSERT INTO user_data_versions (user_id) SELECT id FROM users")
    op.execute(
        """
        CREATE FUNCTION create_user_data_version() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          INSERT INTO user_data_versions (user_id) VALUES (NEW.id) ON CONFLICT DO NOTHING;
          RETURN NULL;
        END $$
        """
    )
    op.execute(
        f"CREATE TRIGGER {CREATE_ROW} AFTER INSERT ON users"
        f" FOR EACH ROW EXECUTE FUNCTION {CREATE_ROW}()"
    )
    # Shared rows (user_id NULL: built-in exercises, cached foods) match no version row.
    op.execute(
        """
        CREATE FUNCTION bump_user_data_version() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          UPDATE user_data_versions SET version = version + 1
          WHERE user_id = CASE WHEN TG_OP = 'DELETE' THEN OLD.user_id ELSE NEW.user_id END;
          RETURN NULL;
        END $$
        """
    )
    for table in VERSIONED_TABLES:
        op.execute(
            f"CREATE TRIGGER {BUMP} AFTER INSERT OR UPDATE OR DELETE ON {table}"
            f" FOR EACH ROW EXECUTE FUNCTION {BUMP}()"
        )
    op.create_index(
        op.f("ix_workout_sets_user_completed_at"), "workout_sets", ["user_id", "completed_at"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_workout_sets_user_completed_at"), table_name="workout_sets")
    for table in VERSIONED_TABLES:
        op.execute(f"DROP TRIGGER {BUMP} ON {table}")
    op.execute(f"DROP FUNCTION {BUMP}()")
    op.execute(f"DROP TRIGGER {CREATE_ROW} ON users")
    op.execute(f"DROP FUNCTION {CREATE_ROW}()")
    op.drop_table("user_data_versions")
