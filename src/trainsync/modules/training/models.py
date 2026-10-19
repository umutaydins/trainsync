"""Exercises, programs, workouts, sets and body metrics (Phase 6, ADR 0017)."""

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from trainsync.core.orm import Base, check_in, utc_timestamp


class Equipment(StrEnum):
    BARBELL = "barbell"
    DUMBBELL = "dumbbell"
    MACHINE = "machine"
    CABLE = "cable"
    BODYWEIGHT = "bodyweight"
    KETTLEBELL = "kettlebell"
    BAND = "band"


class Muscle(StrEnum):
    CHEST = "chest"
    BACK = "back"
    SHOULDERS = "shoulders"
    BICEPS = "biceps"
    TRICEPS = "triceps"
    FOREARMS = "forearms"
    QUADS = "quads"
    HAMSTRINGS = "hamstrings"
    GLUTES = "glutes"
    CALVES = "calves"
    CORE = "core"


LOWER_BODY = frozenset({Muscle.QUADS, Muscle.HAMSTRINGS, Muscle.GLUTES, Muscle.CALVES})


class MovementPattern(StrEnum):
    """What the program generator (P6.3) picks exercises by; null for custom exercises."""

    SQUAT = "squat"
    HINGE = "hinge"
    LUNGE = "lunge"
    HORIZONTAL_PUSH = "horizontal_push"
    VERTICAL_PUSH = "vertical_push"
    HORIZONTAL_PULL = "horizontal_pull"
    VERTICAL_PULL = "vertical_pull"
    CHEST_FLY = "chest_fly"
    LATERAL_RAISE = "lateral_raise"
    REAR_DELT = "rear_delt"
    BICEPS = "biceps"
    TRICEPS = "triceps"
    KNEE_EXTENSION = "knee_extension"
    KNEE_FLEXION = "knee_flexion"
    CALF_RAISE = "calf_raise"
    CORE = "core"


class ProgramGoal(StrEnum):
    STRENGTH = "strength"
    HYPERTROPHY = "hypertrophy"
    GENERAL = "general"


class Progression(StrEnum):
    DOUBLE = "double"  # add weight once every set hits rep_max (P6.3)
    NONE = "none"


class Exercise(Base):
    __tablename__ = "exercises"
    __table_args__ = (
        CheckConstraint(check_in("primary_muscle", Muscle), name="primary_muscle"),
        CheckConstraint(check_in("equipment", Equipment), name="equipment"),
        CheckConstraint(
            f"movement_pattern IS NULL OR {check_in('movement_pattern', MovementPattern)}",
            name="movement_pattern",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(Text)
    primary_muscle: Mapped[str] = mapped_column(String(16))
    secondary_muscles: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)), server_default=text("'{}'")
    )
    equipment: Mapped[str] = mapped_column(String(16))
    movement_pattern: Mapped[str | None] = mapped_column(String(32))
    is_custom: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = utc_timestamp(default_now=True)


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = (
        CheckConstraint(check_in("goal", ProgramGoal), name="goal"),
        CheckConstraint("days_per_week BETWEEN 1 AND 7", name="days_per_week"),
        CheckConstraint("weeks >= 1", name="weeks"),
        # At most one active program.
        Index("uq_programs_active", "active", unique=True, postgresql_where=text("active")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(String(16))
    days_per_week: Mapped[int] = mapped_column(Integer)
    weeks: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = utc_timestamp(default_now=True)


class ProgramDay(Base):
    __tablename__ = "program_days"
    __table_args__ = (
        UniqueConstraint("program_id", "day_index"),
        CheckConstraint("weekday IS NULL OR weekday BETWEEN 0 AND 6", name="weekday"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    program_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("programs.id", ondelete="CASCADE")
    )
    day_index: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    # When the coach expects this day (P6.11, ADR 0030): weekday 0 = Monday, local start time
    # (CHECKIN_TZ). Null = the default spread by days_per_week and WORKOUT_REMINDER_TIME.
    weekday: Mapped[int | None] = mapped_column(Integer)
    start_time: Mapped[time | None] = mapped_column(Time)


class ProgramExercise(Base):
    __tablename__ = "program_exercises"
    __table_args__ = (
        CheckConstraint(check_in("progression", Progression), name="progression"),
        CheckConstraint("sets >= 1 AND rep_min >= 1 AND rep_max >= rep_min", name="sets_reps"),
        CheckConstraint("rest_seconds >= 0", name="rest_seconds"),
        Index("ix_program_exercises_day_position", "program_day_id", "position"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    program_day_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("program_days.id", ondelete="CASCADE")
    )
    exercise_id: Mapped[int] = mapped_column(Integer, ForeignKey("exercises.id"))
    position: Mapped[int] = mapped_column(Integer)
    sets: Mapped[int] = mapped_column(Integer)
    rep_min: Mapped[int] = mapped_column(Integer)
    rep_max: Mapped[int] = mapped_column(Integer)
    rest_seconds: Mapped[int] = mapped_column(Integer)
    start_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    progression: Mapped[str] = mapped_column(String(16), server_default=text("'double'"))


class Workout(Base):
    __tablename__ = "workouts"
    __table_args__ = (Index("ix_workouts_started_at", text("started_at DESC"), "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Client-generated, so a retried or double-tapped start is one workout (ADR 0017).
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    program_day_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("program_days.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime] = utc_timestamp()
    ended_at: Mapped[datetime | None] = utc_timestamp(nullable=True)
    notes: Mapped[str] = mapped_column(Text, server_default=text("''"))
    # A link to a synced activity, not a foreign key: activities can be deleted and re-synced.
    strava_activity_id: Mapped[int | None] = mapped_column(BigInteger)


class WorkoutSet(Base):
    """`client_id` is generated by the client, so a retried or double-tapped log is one row."""

    __tablename__ = "workout_sets"
    __table_args__ = (
        CheckConstraint("reps BETWEEN 0 AND 100", name="reps"),
        CheckConstraint("weight_kg BETWEEN 0 AND 500", name="weight_kg"),
        CheckConstraint("rpe IS NULL OR rpe BETWEEN 1 AND 10", name="rpe"),
        CheckConstraint("rest_seconds IS NULL OR rest_seconds >= 0", name="rest_seconds"),
        Index("ix_workout_sets_workout_id", "workout_id", "exercise_id", "set_index"),
        Index("ix_workout_sets_exercise_completed_at", "exercise_id", "completed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    workout_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workouts.id", ondelete="CASCADE")
    )
    exercise_id: Mapped[int] = mapped_column(Integer, ForeignKey("exercises.id"))
    set_index: Mapped[int] = mapped_column(Integer)
    reps: Mapped[int] = mapped_column(Integer)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    rpe: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    is_warmup: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    completed_at: Mapped[datetime] = utc_timestamp()
    # Actual rest before this set, as measured by the client.
    rest_seconds: Mapped[int | None] = mapped_column(Integer)


class BodyMetric(Base):
    """Only what the user enters; nothing is derived or estimated."""

    __tablename__ = "body_metrics"
    __table_args__ = (CheckConstraint("weight_kg > 0 AND weight_kg < 500", name="weight_kg"),)

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(5, 2))
