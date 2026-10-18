"""SQLAlchemy models for every table in docs/architecture.md → Data model."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class SyncKind(StrEnum):
    BACKFILL = "backfill"
    INCREMENTAL = "incremental"


class SyncStatus(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WebhookStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class NotificationKind(StrEnum):
    NEW_ACTIVITY = "new_activity"
    # Daily check-in (P6.9, ADR 0020); object_id is the local date as yyyymmdd.
    CHECKIN_PROMPT = "checkin_prompt"
    CHECKIN_REMINDER = "checkin_reminder"


class CheckinStatus(StrEnum):
    DONE = "done"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    REST = "rest"
    SICK_OR_INJURED = "sick_or_injured"


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


class FoodSource(StrEnum):
    MANUAL = "manual"
    OPENFOODFACTS = "openfoodfacts"


class Meal(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class Sex(StrEnum):
    """Only what the Mifflin-St Jeor equation distinguishes."""

    MALE = "male"
    FEMALE = "female"


class ActivityBaseline(StrEnum):
    """Everyday activity outside logged exercise; picks the BMR multiplier (P6.4)."""

    SEDENTARY = "sedentary"
    LIGHT = "light"
    MODERATE = "moderate"


def _check_in(column: str, enum: type[StrEnum]) -> str:
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"


def _utc_timestamp(*, nullable: bool = False, default_now: bool = False) -> Any:
    return mapped_column(
        DateTime(timezone=True),
        nullable=nullable,
        server_default=func.now() if default_now else None,
    )


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSONB}


class Athlete(Base):
    __tablename__ = "athletes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strava_athlete_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = _utc_timestamp(default_now=True)


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    athlete_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("athletes.id", ondelete="CASCADE"), primary_key=True
    )
    access_token_enc: Mapped[bytes] = mapped_column(LargeBinary)
    refresh_token_enc: Mapped[bytes] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime] = _utc_timestamp()
    scope: Mapped[str] = mapped_column(Text)


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        Index("ix_activities_athlete_start_date", "athlete_id", text("start_date DESC")),
        Index("ix_activities_athlete_sport_start_date", "athlete_id", "sport_type", "start_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strava_activity_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    athlete_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("athletes.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(Text)
    sport_type: Mapped[str] = mapped_column(String(64))
    start_date: Mapped[datetime] = _utc_timestamp()
    distance_m: Mapped[float] = mapped_column(Float)
    moving_time_s: Mapped[int] = mapped_column(Integer)
    elapsed_time_s: Mapped[int] = mapped_column(Integer)
    elevation_gain_m: Mapped[float] = mapped_column(Float)
    average_heartrate: Mapped[float | None] = mapped_column(Float)
    raw: Mapped[dict[str, Any]]
    deleted_at: Mapped[datetime | None] = _utc_timestamp(nullable=True)
    synced_at: Mapped[datetime] = _utc_timestamp(default_now=True)


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint(_check_in("kind", SyncKind), name="kind"),
        CheckConstraint(_check_in("status", SyncStatus), name="status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("athletes.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    cursor: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    pages: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    upserted: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = _utc_timestamp(default_now=True)
    # Heartbeat, bumped with every checkpoint: tells a live run from one whose worker died.
    updated_at: Mapped[datetime] = _utc_timestamp(default_now=True)
    finished_at: Mapped[datetime | None] = _utc_timestamp(nullable=True)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        CheckConstraint(_check_in("status", WebhookStatus), name="status"),
        Index("ix_webhook_events_status_received_at", "status", "received_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dedup_key: Mapped[str] = mapped_column(String(64), unique=True)
    payload: Mapped[dict[str, Any]]
    status: Mapped[str] = mapped_column(String(16), server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    received_at: Mapped[datetime] = _utc_timestamp(default_now=True)
    # Set on every claim; drives the retry backoff and the stuck-in-processing check.
    last_attempt_at: Mapped[datetime | None] = _utc_timestamp(nullable=True)
    processed_at: Mapped[datetime | None] = _utc_timestamp(nullable=True)


class Notification(Base):
    """One row per notification ever sent: the unique `(kind, object_id)` makes sending
    idempotent (claimed before sending, released if the send fails; ADR 0012)."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(_check_in("kind", NotificationKind), name="kind"),
        UniqueConstraint("kind", "object_id", name="uq_notifications_kind_object_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[int] = mapped_column(BigInteger)
    sent_at: Mapped[datetime] = _utc_timestamp(default_now=True)


# ---------------------------------------------------------------- training (Phase 6)
# Single-user like the rest of the personal data: no athlete_id on these tables.


class Exercise(Base):
    __tablename__ = "exercises"
    __table_args__ = (
        CheckConstraint(_check_in("primary_muscle", Muscle), name="primary_muscle"),
        CheckConstraint(_check_in("equipment", Equipment), name="equipment"),
        CheckConstraint(
            f"movement_pattern IS NULL OR {_check_in('movement_pattern', MovementPattern)}",
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
    created_at: Mapped[datetime] = _utc_timestamp(default_now=True)


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = (
        CheckConstraint(_check_in("goal", ProgramGoal), name="goal"),
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
    created_at: Mapped[datetime] = _utc_timestamp(default_now=True)


class ProgramDay(Base):
    __tablename__ = "program_days"
    __table_args__ = (UniqueConstraint("program_id", "day_index"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    program_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("programs.id", ondelete="CASCADE")
    )
    day_index: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)


class ProgramExercise(Base):
    __tablename__ = "program_exercises"
    __table_args__ = (
        CheckConstraint(_check_in("progression", Progression), name="progression"),
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
    program_day_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("program_days.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime] = _utc_timestamp()
    ended_at: Mapped[datetime | None] = _utc_timestamp(nullable=True)
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
    completed_at: Mapped[datetime] = _utc_timestamp()
    # Actual rest before this set, as measured by the client.
    rest_seconds: Mapped[int | None] = mapped_column(Integer)


class BodyMetric(Base):
    """Only what the user enters; nothing is derived or estimated."""

    __tablename__ = "body_metrics"
    __table_args__ = (CheckConstraint("weight_kg > 0 AND weight_kg < 500", name="weight_kg"),)

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(5, 2))


class DailyCheckin(Base):
    """The evening report of one local day (P6.9, ADR 0020): did the owner train, and how it
    went. One row per date; `PUT /v1/checkins/{date}` upserts it."""

    __tablename__ = "daily_checkins"
    __table_args__ = (
        CheckConstraint(_check_in("status", CheckinStatus), name="status"),
        CheckConstraint("sleep_hours IS NULL OR sleep_hours BETWEEN 0 AND 24", name="sleep_hours"),
        CheckConstraint("energy_1_5 IS NULL OR energy_1_5 BETWEEN 1 AND 5", name="energy_1_5"),
        CheckConstraint(
            "body_weight_kg IS NULL OR (body_weight_kg > 0 AND body_weight_kg < 500)",
            name="body_weight_kg",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, unique=True)
    status: Mapped[str] = mapped_column(String(16))
    workout_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("workouts.id", ondelete="SET NULL")
    )
    reason_note: Mapped[str | None] = mapped_column(Text)
    sleep_hours: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    energy_1_5: Mapped[int | None] = mapped_column(Integer)
    body_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = _utc_timestamp(default_now=True)
    updated_at: Mapped[datetime] = _utc_timestamp(default_now=True)


# ---------------------------------------------------------------- nutrition (Phase 6)
# Single user, like training. Energy-balance math lives in trainsync.nutrition.energy (ADR 0019).


class Food(Base):
    """Per-100 g values. Open Food Facts results are cached here (`source=openfoodfacts`,
    unique `barcode`); macros can be unknown (null), kcal cannot."""

    __tablename__ = "foods"
    __table_args__ = (
        CheckConstraint(_check_in("source", FoodSource), name="source"),
        CheckConstraint("kcal_100g >= 0 AND kcal_100g <= 1000", name="kcal_100g"),
        CheckConstraint(
            "(protein_100g IS NULL OR protein_100g BETWEEN 0 AND 100)"
            " AND (carbs_100g IS NULL OR carbs_100g BETWEEN 0 AND 100)"
            " AND (fat_100g IS NULL OR fat_100g BETWEEN 0 AND 100)",
            name="macros_100g",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(Text)
    barcode: Mapped[str | None] = mapped_column(String(14), unique=True)
    kcal_100g: Mapped[Decimal] = mapped_column(Numeric(6, 1))
    protein_100g: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    carbs_100g: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    fat_100g: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    source: Mapped[str] = mapped_column(String(16), server_default=text("'manual'"))
    favorite: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = _utc_timestamp(default_now=True)


class FoodLog(Base):
    """`client_id` is generated by the client, so a retried log is one row (like sets).

    The food's per-100 g values are copied in at log time, so editing a food later does not
    change past days (summaries read these columns, never the food's current values).
    """

    __tablename__ = "food_logs"
    __table_args__ = (
        CheckConstraint(_check_in("meal", Meal), name="meal"),
        CheckConstraint("grams > 0 AND grams <= 5000", name="grams"),
        Index("ix_food_logs_date", "date", "meal"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    date: Mapped[date] = mapped_column(Date)
    meal: Mapped[str] = mapped_column(String(16))
    food_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("foods.id"))
    grams: Mapped[Decimal] = mapped_column(Numeric(6, 1))
    kcal_100g: Mapped[Decimal] = mapped_column(Numeric(6, 1))
    protein_100g: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    carbs_100g: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    fat_100g: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    created_at: Mapped[datetime] = _utc_timestamp(default_now=True)


class NutritionProfile(Base):
    """The single profile row (`id` is always 1). Body weight is not here: it comes from
    `body_metrics`, the latest entry on or before the day being estimated."""

    __tablename__ = "nutrition_profile"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint(_check_in("sex", Sex), name="sex"),
        CheckConstraint(_check_in("activity_baseline", ActivityBaseline), name="activity_baseline"),
        CheckConstraint("birth_year BETWEEN 1900 AND 2100", name="birth_year"),
        CheckConstraint("height_cm BETWEEN 100 AND 250", name="height_cm"),
        CheckConstraint("kcal_target IS NULL OR kcal_target > 0", name="kcal_target"),
        CheckConstraint(
            "protein_target_g IS NULL OR protein_target_g >= 0", name="protein_target_g"
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=False, server_default=text("1")
    )
    sex: Mapped[str] = mapped_column(String(8))
    birth_year: Mapped[int] = mapped_column(Integer)
    height_cm: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    activity_baseline: Mapped[str] = mapped_column(String(16))
    kcal_target: Mapped[int | None] = mapped_column(Integer)
    protein_target_g: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = _utc_timestamp(default_now=True)
