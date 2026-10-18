"""training: exercises (seeded), programs, workouts, sets, body metrics

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-18
"""

import json
from collections.abc import Sequence
from importlib import resources

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MUSCLES = (
    "'chest', 'back', 'shoulders', 'biceps', 'triceps', 'forearms', 'quads', 'hamstrings', "
    "'glutes', 'calves', 'core'"
)
EQUIPMENT = "'barbell', 'dumbbell', 'machine', 'cable', 'bodyweight', 'kettlebell', 'band'"
PATTERNS = (
    "'squat', 'hinge', 'lunge', 'horizontal_push', 'vertical_push', 'horizontal_pull', "
    "'vertical_pull', 'chest_fly', 'lateral_raise', 'rear_delt', 'biceps', 'triceps', "
    "'knee_extension', 'knee_flexion', 'calf_raise', 'core'"
)


def _now() -> sa.TextClause:
    return sa.text("now()")


def upgrade() -> None:
    exercises = op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("primary_muscle", sa.String(length=16), nullable=False),
        sa.Column(
            "secondary_muscles",
            postgresql.ARRAY(sa.String(length=16)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("equipment", sa.String(length=16), nullable=False),
        sa.Column("movement_pattern", sa.String(length=32), nullable=True),
        sa.Column("is_custom", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.CheckConstraint(
            f"primary_muscle IN ({MUSCLES})", name=op.f("ck_exercises_primary_muscle")
        ),
        sa.CheckConstraint(f"equipment IN ({EQUIPMENT})", name=op.f("ck_exercises_equipment")),
        sa.CheckConstraint(
            f"movement_pattern IS NULL OR movement_pattern IN ({PATTERNS})",
            name=op.f("ck_exercises_movement_pattern"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exercises")),
        sa.UniqueConstraint("slug", name=op.f("uq_exercises_slug")),
    )
    op.create_table(
        "programs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("goal", sa.String(length=16), nullable=False),
        sa.Column("days_per_week", sa.Integer(), nullable=False),
        sa.Column("weeks", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.CheckConstraint(
            "goal IN ('strength', 'hypertrophy', 'general')", name=op.f("ck_programs_goal")
        ),
        sa.CheckConstraint("days_per_week BETWEEN 1 AND 7", name=op.f("ck_programs_days_per_week")),
        sa.CheckConstraint("weeks >= 1", name=op.f("ck_programs_weeks")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_programs")),
    )
    op.create_index(
        "uq_programs_active",
        "programs",
        ["active"],
        unique=True,
        postgresql_where=sa.text("active"),
    )
    op.create_table(
        "program_days",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("program_id", sa.BigInteger(), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name=op.f("fk_program_days_program_id_programs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_program_days")),
        sa.UniqueConstraint("program_id", "day_index", name=op.f("uq_program_days_program_id")),
    )
    op.create_table(
        "program_exercises",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("program_day_id", sa.BigInteger(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=False),
        sa.Column("rep_min", sa.Integer(), nullable=False),
        sa.Column("rep_max", sa.Integer(), nullable=False),
        sa.Column("rest_seconds", sa.Integer(), nullable=False),
        sa.Column("start_weight_kg", sa.Numeric(6, 2), nullable=True),
        sa.Column(
            "progression", sa.String(length=16), server_default=sa.text("'double'"), nullable=False
        ),
        sa.CheckConstraint(
            "progression IN ('double', 'none')", name=op.f("ck_program_exercises_progression")
        ),
        sa.CheckConstraint(
            "sets >= 1 AND rep_min >= 1 AND rep_max >= rep_min",
            name=op.f("ck_program_exercises_sets_reps"),
        ),
        sa.CheckConstraint("rest_seconds >= 0", name=op.f("ck_program_exercises_rest_seconds")),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.id"],
            name=op.f("fk_program_exercises_exercise_id_exercises"),
        ),
        sa.ForeignKeyConstraint(
            ["program_day_id"],
            ["program_days.id"],
            name=op.f("fk_program_exercises_program_day_id_program_days"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_program_exercises")),
    )
    op.create_index(
        "ix_program_exercises_day_position",
        "program_exercises",
        ["program_day_id", "position"],
    )
    op.create_table(
        "workouts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("program_day_id", sa.BigInteger(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("strava_activity_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["program_day_id"],
            ["program_days.id"],
            name=op.f("fk_workouts_program_day_id_program_days"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workouts")),
    )
    op.create_index(
        "ix_workouts_started_at", "workouts", [sa.text("started_at DESC"), "id"], unique=False
    )
    op.create_table(
        "workout_sets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("workout_id", sa.BigInteger(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("set_index", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(6, 2), nullable=False),
        sa.Column("rpe", sa.Numeric(3, 1), nullable=True),
        sa.Column("is_warmup", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rest_seconds", sa.Integer(), nullable=True),
        sa.CheckConstraint("reps BETWEEN 0 AND 100", name=op.f("ck_workout_sets_reps")),
        sa.CheckConstraint("weight_kg BETWEEN 0 AND 500", name=op.f("ck_workout_sets_weight_kg")),
        sa.CheckConstraint("rpe IS NULL OR rpe BETWEEN 1 AND 10", name=op.f("ck_workout_sets_rpe")),
        sa.CheckConstraint(
            "rest_seconds IS NULL OR rest_seconds >= 0", name=op.f("ck_workout_sets_rest_seconds")
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["exercises.id"], name=op.f("fk_workout_sets_exercise_id_exercises")
        ),
        sa.ForeignKeyConstraint(
            ["workout_id"],
            ["workouts.id"],
            name=op.f("fk_workout_sets_workout_id_workouts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workout_sets")),
        sa.UniqueConstraint("client_id", name=op.f("uq_workout_sets_client_id")),
    )
    op.create_index(
        "ix_workout_sets_workout_id", "workout_sets", ["workout_id", "exercise_id", "set_index"]
    )
    op.create_index(
        "ix_workout_sets_exercise_completed_at", "workout_sets", ["exercise_id", "completed_at"]
    )
    op.create_table(
        "body_metrics",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(5, 2), nullable=False),
        sa.CheckConstraint(
            "weight_kg > 0 AND weight_kg < 500", name=op.f("ck_body_metrics_weight_kg")
        ),
        sa.PrimaryKeyConstraint("date", name=op.f("pk_body_metrics")),
    )

    # Data migration: the built-in exercise library.
    seed = resources.files("trainsync.training").joinpath("seed_exercises.json")
    op.bulk_insert(exercises, json.loads(seed.read_text(encoding="utf-8")))


def downgrade() -> None:
    op.drop_table("body_metrics")
    op.drop_index("ix_workout_sets_exercise_completed_at", table_name="workout_sets")
    op.drop_index("ix_workout_sets_workout_id", table_name="workout_sets")
    op.drop_table("workout_sets")
    op.drop_index("ix_workouts_started_at", table_name="workouts")
    op.drop_table("workouts")
    op.drop_index("ix_program_exercises_day_position", table_name="program_exercises")
    op.drop_table("program_exercises")
    op.drop_table("program_days")
    op.drop_index("uq_programs_active", table_name="programs")
    op.drop_table("programs")
    op.drop_table("exercises")
