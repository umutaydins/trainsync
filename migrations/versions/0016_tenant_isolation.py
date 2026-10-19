"""user_id on every user-owned table; existing rows go to the owner (P8.2, ADR 0035)

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-19

The single-user data becomes the owner's: when any user-owned row exists and no owner account
does, `OWNER_EMAIL` must be set and the owner is created with an unusable password
(`scripts/owner.py set-password` sets it). Postgres runs the whole migration in one
transaction, so a failure leaves nothing half-done and a re-run starts clean; the data steps only
touch rows whose `user_id` is still null.
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Rollback (ADR 0026): downgrade() restores the single-user schema with the owner's rows; it
# refuses to run while another user owns data (that would merge two people's data).
reversible: bool = True

UNUSABLE_HASH = "!unusable"
# Every user-owned table whose rows all belong to the owner after the upgrade.
OWNED = (
    "athletes",
    "oauth_tokens",
    "activities",
    "sync_runs",
    "programs",
    "program_days",
    "program_exercises",
    "workouts",
    "workout_sets",
    "body_metrics",
    "daily_checkins",
    "food_logs",
    "nutrition_profile",
    "notifications",
)
# Shared tables where only some rows are the owner's (custom exercises, manual foods).
PARTLY_OWNED = {"exercises": "is_custom", "foods": "source = 'manual'"}


def _fk(table: str) -> str:
    return f"fk_{table}_user_id_users"


def _owner_id(conn: sa.Connection) -> int | None:
    owner = conn.execute(sa.text("SELECT id FROM users WHERE role = 'owner'")).scalar()
    if owner is not None:
        return int(owner)
    # The built-in exercise library (migration 0005) is shared, not the owner's data.
    checks = {**dict.fromkeys(OWNED, "true"), **PARTLY_OWNED}
    has_data = any(
        conn.execute(
            sa.text(f"SELECT EXISTS (SELECT 1 FROM {table} WHERE {mine})")  # noqa: S608
        ).scalar()
        for table, mine in checks.items()
    )
    if not has_data:
        return None
    email = os.environ.get("OWNER_EMAIL", "").strip().lower()
    if not email:
        raise RuntimeError(
            "migration 0016: the database has single-user data; set OWNER_EMAIL so it can be "
            "assigned to the owner account"
        )
    return int(
        conn.execute(
            sa.text(
                "INSERT INTO users (email, password_hash, display_name, role, timezone)"
                " VALUES (:email, :hash, :name, 'owner', :zone) RETURNING id"
            ),
            {
                "email": email,
                "hash": UNUSABLE_HASH,
                "name": email.split("@", 1)[0],
                "zone": os.environ.get("CHECKIN_TZ", "UTC") or "UTC",
            },
        ).scalar_one()
    )


def _add_owner_column(table: str, owner: int | None, *, nullable: bool, where: str = "") -> None:
    op.add_column(table, sa.Column("user_id", sa.BigInteger(), nullable=True))
    if owner is not None:
        condition = f" AND ({where})" if where else ""
        # Table names and conditions are this module's constants, never input.
        statement = f"UPDATE {table} SET user_id = :owner WHERE user_id IS NULL{condition}"  # noqa: S608
        op.execute(sa.text(statement).bindparams(owner=owner))
    if not nullable:
        op.alter_column(table, "user_id", nullable=False)
    op.create_foreign_key(op.f(_fk(table)), table, "users", ["user_id"], ["id"], ondelete="CASCADE")


def upgrade() -> None:
    owner = _owner_id(op.get_bind())
    for table in OWNED:
        _add_owner_column(table, owner, nullable=False)
    for table, mine in PARTLY_OWNED.items():
        _add_owner_column(table, owner, nullable=True, where=mine)

    # Strava: one athlete per user; tokens and runs carry the user too.
    op.create_unique_constraint(op.f("uq_athletes_user_id"), "athletes", ["user_id"])
    op.create_index(op.f("ix_oauth_tokens_user_id"), "oauth_tokens", ["user_id"])
    op.create_index(
        op.f("ix_activities_user_start_date"), "activities", ["user_id", sa.text("start_date DESC")]
    )
    op.create_index(op.f("ix_sync_runs_user_id"), "sync_runs", ["user_id"])

    # Training.
    op.drop_constraint(op.f("uq_exercises_slug"), "exercises", type_="unique")
    op.create_index(
        op.f("uq_exercises_shared_slug"),
        "exercises",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )
    op.create_unique_constraint(op.f("uq_exercises_user_slug"), "exercises", ["user_id", "slug"])
    op.drop_index(op.f("uq_programs_active"), table_name="programs")
    op.create_index(
        op.f("uq_programs_active"),
        "programs",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("active"),
    )
    op.create_index(op.f("ix_programs_user_id"), "programs", ["user_id", "created_at"])
    op.create_index(op.f("ix_program_days_user_id"), "program_days", ["user_id"])
    op.create_index(op.f("ix_program_exercises_user_id"), "program_exercises", ["user_id"])
    op.drop_constraint(op.f("uq_workouts_client_id"), "workouts", type_="unique")
    op.create_unique_constraint(
        op.f("uq_workouts_user_client_id"), "workouts", ["user_id", "client_id"]
    )
    op.drop_index(op.f("ix_workouts_started_at"), table_name="workouts")
    op.create_index(
        op.f("ix_workouts_started_at"), "workouts", ["user_id", sa.text("started_at DESC"), "id"]
    )
    op.drop_constraint(op.f("uq_workout_sets_client_id"), "workout_sets", type_="unique")
    op.create_unique_constraint(
        op.f("uq_workout_sets_user_client_id"), "workout_sets", ["user_id", "client_id"]
    )
    op.drop_index(op.f("ix_workout_sets_exercise_completed_at"), table_name="workout_sets")
    op.create_index(
        op.f("ix_workout_sets_exercise_completed_at"),
        "workout_sets",
        ["user_id", "exercise_id", "completed_at"],
    )
    op.drop_constraint(op.f("pk_body_metrics"), "body_metrics", type_="primary")
    op.create_primary_key(op.f("pk_body_metrics"), "body_metrics", ["user_id", "date"])
    op.drop_constraint(op.f("uq_daily_checkins_date"), "daily_checkins", type_="unique")
    op.create_unique_constraint(
        op.f("uq_daily_checkins_user_date"), "daily_checkins", ["user_id", "date"]
    )

    # Nutrition: foods are shared or private, favourites per user, one profile per user.
    op.drop_constraint(op.f("uq_foods_barcode"), "foods", type_="unique")
    op.create_index(
        op.f("uq_foods_shared_barcode"),
        "foods",
        ["barcode"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )
    op.create_unique_constraint(op.f("uq_foods_user_barcode"), "foods", ["user_id", "barcode"])
    op.create_table(
        "food_favorites",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("food_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["food_id"],
            ["foods.id"],
            name=op.f("fk_food_favorites_food_id_foods"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_food_favorites_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "food_id", name=op.f("pk_food_favorites")),
    )
    if owner is not None:
        op.execute(
            sa.text(
                "INSERT INTO food_favorites (user_id, food_id)"
                " SELECT :owner, id FROM foods WHERE favorite"
            ).bindparams(owner=owner)
        )
    op.drop_column("foods", "favorite")
    op.drop_constraint(op.f("uq_food_logs_client_id"), "food_logs", type_="unique")
    op.create_unique_constraint(
        op.f("uq_food_logs_user_client_id"), "food_logs", ["user_id", "client_id"]
    )
    op.drop_index(op.f("ix_food_logs_date"), table_name="food_logs")
    op.create_index(op.f("ix_food_logs_date"), "food_logs", ["user_id", "date", "meal"])
    op.drop_constraint(op.f("ck_nutrition_profile_single_row"), "nutrition_profile", type_="check")
    op.drop_constraint(op.f("pk_nutrition_profile"), "nutrition_profile", type_="primary")
    op.drop_column("nutrition_profile", "id")
    op.create_primary_key(op.f("pk_nutrition_profile"), "nutrition_profile", ["user_id"])

    # Notifications: claimed per user.
    op.drop_constraint(op.f("uq_notifications_kind_object_id"), "notifications", type_="unique")
    op.create_unique_constraint(
        op.f("uq_notifications_user_kind_object_id"),
        "notifications",
        ["user_id", "kind", "object_id"],
    )


def _refuse_if_shared() -> None:
    conn = op.get_bind()
    owners = set()
    for table in (*OWNED, *PARTLY_OWNED):
        rows = conn.execute(
            sa.text(f"SELECT DISTINCT user_id FROM {table} WHERE user_id IS NOT NULL")  # noqa: S608
        )
        owners.update(row[0] for row in rows)
    if len(owners) > 1:
        raise RuntimeError(
            "migration 0016 downgrade: more than one user owns data; downgrading would merge "
            "their data into one single-user database"
        )


def downgrade() -> None:
    _refuse_if_shared()
    op.drop_constraint(
        op.f("uq_notifications_user_kind_object_id"), "notifications", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_notifications_kind_object_id"), "notifications", ["kind", "object_id"]
    )

    op.drop_constraint(op.f("pk_nutrition_profile"), "nutrition_profile", type_="primary")
    op.add_column(
        "nutrition_profile",
        sa.Column("id", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.create_primary_key(op.f("pk_nutrition_profile"), "nutrition_profile", ["id"])
    op.create_check_constraint(
        op.f("ck_nutrition_profile_single_row"), "nutrition_profile", "id = 1"
    )
    op.drop_index(op.f("ix_food_logs_date"), table_name="food_logs")
    op.create_index(op.f("ix_food_logs_date"), "food_logs", ["date", "meal"])
    op.drop_constraint(op.f("uq_food_logs_user_client_id"), "food_logs", type_="unique")
    op.create_unique_constraint(op.f("uq_food_logs_client_id"), "food_logs", ["client_id"])
    op.add_column(
        "foods",
        sa.Column("favorite", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.execute("UPDATE foods SET favorite = true WHERE id IN (SELECT food_id FROM food_favorites)")
    op.drop_table("food_favorites")
    op.drop_constraint(op.f("uq_foods_user_barcode"), "foods", type_="unique")
    op.drop_index(op.f("uq_foods_shared_barcode"), table_name="foods")
    op.create_unique_constraint(op.f("uq_foods_barcode"), "foods", ["barcode"])

    op.drop_constraint(op.f("uq_daily_checkins_user_date"), "daily_checkins", type_="unique")
    op.create_unique_constraint(op.f("uq_daily_checkins_date"), "daily_checkins", ["date"])
    op.drop_constraint(op.f("pk_body_metrics"), "body_metrics", type_="primary")
    op.create_primary_key(op.f("pk_body_metrics"), "body_metrics", ["date"])
    op.drop_index(op.f("ix_workout_sets_exercise_completed_at"), table_name="workout_sets")
    op.create_index(
        op.f("ix_workout_sets_exercise_completed_at"),
        "workout_sets",
        ["exercise_id", "completed_at"],
    )
    op.drop_constraint(op.f("uq_workout_sets_user_client_id"), "workout_sets", type_="unique")
    op.create_unique_constraint(op.f("uq_workout_sets_client_id"), "workout_sets", ["client_id"])
    op.drop_index(op.f("ix_workouts_started_at"), table_name="workouts")
    op.create_index(op.f("ix_workouts_started_at"), "workouts", [sa.text("started_at DESC"), "id"])
    op.drop_constraint(op.f("uq_workouts_user_client_id"), "workouts", type_="unique")
    op.create_unique_constraint(op.f("uq_workouts_client_id"), "workouts", ["client_id"])
    op.drop_index(op.f("ix_program_exercises_user_id"), table_name="program_exercises")
    op.drop_index(op.f("ix_program_days_user_id"), table_name="program_days")
    op.drop_index(op.f("ix_programs_user_id"), table_name="programs")
    op.drop_index(op.f("uq_programs_active"), table_name="programs")
    op.create_index(
        op.f("uq_programs_active"),
        "programs",
        ["active"],
        unique=True,
        postgresql_where=sa.text("active"),
    )
    op.drop_constraint(op.f("uq_exercises_user_slug"), "exercises", type_="unique")
    op.drop_index(op.f("uq_exercises_shared_slug"), table_name="exercises")
    op.create_unique_constraint(op.f("uq_exercises_slug"), "exercises", ["slug"])

    op.drop_index(op.f("ix_sync_runs_user_id"), table_name="sync_runs")
    op.drop_index(op.f("ix_activities_user_start_date"), table_name="activities")
    op.drop_index(op.f("ix_oauth_tokens_user_id"), table_name="oauth_tokens")
    op.drop_constraint(op.f("uq_athletes_user_id"), "athletes", type_="unique")

    for table in (*PARTLY_OWNED, *reversed(OWNED)):
        op.drop_constraint(op.f(_fk(table)), table, type_="foreignkey")
        op.drop_column(table, "user_id")
