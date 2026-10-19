"""Wipe the demo database and write the dataset of `trainsync.entrypoints.demo.seed` (one
transaction).

Straight through the ORM and the repositories, never over HTTP: the API refuses every write in
demo mode. `reset` refuses to run unless `DEMO_MODE` is on, so it can never wipe a real database.
"""

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.clock import Clock
from trainsync.core.logging import get_logger
from trainsync.core.security import hash_password
from trainsync.core.settings import Settings
from trainsync.entrypoints.demo import seed
from trainsync.entrypoints.demo.seed import DemoDataset
from trainsync.modules.activities.repository import ActivityRepository
from trainsync.modules.auth.models import User, UserRole
from trainsync.modules.auth.repository import UserRepository
from trainsync.modules.checkin.models import DailyCheckin
from trainsync.modules.models import Base
from trainsync.modules.nutrition.models import Food, FoodFavorite, FoodLog, NutritionProfile
from trainsync.modules.strava.models import Athlete
from trainsync.modules.sync.models import SyncKind, SyncRun, SyncStatus
from trainsync.modules.training.models import (
    BodyMetric,
    Exercise,
    Program,
    ProgramDay,
    ProgramExercise,
    Workout,
    WorkoutSet,
)

log = get_logger(__name__)

# The demo's one account (a reserved .invalid domain, never a real address); it is the owner,
# so the demo's API key reads its data. Its password is public on purpose (README "Live demo"):
# the demo is read-only and wiped every night.
DEMO_EMAIL = "demo@trainsync.invalid"
DEMO_PASSWORD = "trainsync-demo"  # noqa: S105  (published demo login, read-only data)
DEMO_DISPLAY_NAME = "Demo athlete"
# The exercise library is seeded by migration 0005; it stays (custom exercises go). `users` is
# emptied with DELETE: a TRUNCATE ... CASCADE of it would also empty the library.
KEPT_TABLES = frozenset({"exercises", "users"})


class DemoModeRequiredError(RuntimeError):
    """`reset` was called without `DEMO_MODE=true`."""


@dataclass(frozen=True, slots=True)
class ResetSummary:
    activities: int
    workouts: int
    sets: int
    checkins: int
    food_logs: int
    body_metrics: int


async def reset(
    settings: Settings, sessionmaker: async_sessionmaker[AsyncSession], clock: Clock
) -> ResetSummary:
    """Delete every row (except the exercise library) and write a fresh dataset for today."""
    if not settings.demo_mode:
        raise DemoModeRequiredError("refusing to wipe the database: DEMO_MODE is not true")
    now = clock()
    data = seed.build_dataset(now, settings.checkin_zone)
    async with sessionmaker.begin() as session:
        await _wipe(session)
        await _write(session, data, now, settings.checkin_tz)
    summary = ResetSummary(
        activities=len(data.activities),
        workouts=len(data.workouts),
        sets=sum(len(w.sets) for w in data.workouts),
        checkins=len(data.checkins),
        food_logs=len(data.food_logs),
        body_metrics=len(data.body_weights),
    )
    log.info("demo_reset", today=data.today.isoformat(), **asdict(summary))
    return summary


async def _wipe(session: AsyncSession) -> None:
    tables = ", ".join(
        table.name for table in Base.metadata.sorted_tables if table.name not in KEPT_TABLES
    )
    await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await session.execute(delete(Exercise).where(Exercise.is_custom))
    await session.execute(delete(User))
    await session.execute(text("ALTER SEQUENCE users_id_seq RESTART"))


async def _write(session: AsyncSession, data: DemoDataset, now: datetime, timezone: str) -> None:
    user = await UserRepository(session).add(
        email=DEMO_EMAIL,
        password_hash=await hash_password(DEMO_PASSWORD),
        display_name=DEMO_DISPLAY_NAME,
        timezone=timezone,
        role=UserRole.OWNER,
    )
    athlete = Athlete(user_id=user.id, strava_athlete_id=seed.DEMO_STRAVA_ATHLETE_ID, active=True)
    session.add(athlete)
    await session.flush()
    await ActivityRepository(session).upsert_many(athlete.id, data.activities)
    session.add_all(_sync_runs(user.id, athlete.id, len(data.activities), now))
    workout_ids = await _write_training(session, user.id, data)
    session.add_all(
        DailyCheckin(
            user_id=user.id,
            date=c.date,
            status=c.status,
            workout_id=workout_ids.get(c.workout) if c.workout else None,
            reason_note=c.reason_note,
            sleep_hours=c.sleep_hours,
            energy_1_5=c.energy_1_5,
            body_weight_kg=c.body_weight_kg,
        )
        for c in data.checkins
    )
    session.add_all(
        BodyMetric(user_id=user.id, date=d, weight_kg=kg) for d, kg in data.body_weights.items()
    )
    await _write_nutrition(session, user.id, data)


def _sync_runs(user_id: int, athlete_id: int, activities: int, now: datetime) -> list[SyncRun]:
    """What a connected account looks like: a finished backfill and a recent incremental run."""
    done = SyncStatus.SUCCEEDED.value
    backfill_at = now - timedelta(weeks=seed.WEEKS, hours=-1)
    incremental_at = now - timedelta(minutes=12)
    return [
        SyncRun(
            user_id=user_id,
            athlete_id=athlete_id,
            kind=SyncKind.BACKFILL.value,
            status=done,
            pages=1,
            upserted=activities,
            started_at=backfill_at,
            updated_at=backfill_at + timedelta(minutes=2),
            finished_at=backfill_at + timedelta(minutes=2),
        ),
        SyncRun(
            user_id=user_id,
            athlete_id=athlete_id,
            kind=SyncKind.INCREMENTAL.value,
            status=done,
            pages=1,
            upserted=0,
            started_at=incremental_at,
            updated_at=incremental_at + timedelta(seconds=3),
            finished_at=incremental_at + timedelta(seconds=3),
        ),
    ]


async def _write_training(
    session: AsyncSession, user_id: int, data: DemoDataset
) -> dict[uuid.UUID, int]:
    slugs = {p.slug for _, _, day in seed.PROGRAM_DAYS for p in day}
    rows = await session.execute(
        select(Exercise.slug, Exercise.id).where(
            Exercise.slug.in_(slugs), Exercise.user_id.is_(None)
        )
    )
    exercise_ids: dict[str, int] = {slug: id_ for slug, id_ in rows.all()}
    missing = slugs - exercise_ids.keys()
    if missing:
        raise RuntimeError(f"exercise library is missing {sorted(missing)}: run the migrations")
    program = Program(
        user_id=user_id,
        name=seed.PROGRAM_NAME,
        goal=seed.PROGRAM_GOAL,
        days_per_week=len(seed.PROGRAM_DAYS),
        weeks=seed.WEEKS,
        active=True,
    )
    session.add(program)
    await session.flush()
    day_ids: list[int] = []
    for index, (name, _, exercises) in enumerate(seed.PROGRAM_DAYS):
        day = ProgramDay(user_id=user_id, program_id=program.id, day_index=index, name=name)
        session.add(day)
        await session.flush()
        day_ids.append(day.id)
        session.add_all(
            ProgramExercise(
                user_id=user_id,
                program_day_id=day.id,
                exercise_id=exercise_ids[p.slug],
                position=position,
                sets=p.sets,
                rep_min=p.rep_min,
                rep_max=p.rep_max,
                rest_seconds=p.rest_seconds,
                start_weight_kg=p.start_kg,
            )
            for position, p in enumerate(exercises)
        )
    workout_ids: dict[uuid.UUID, int] = {}
    for w in data.workouts:
        workout = Workout(
            user_id=user_id,
            client_id=w.client_id,
            program_day_id=day_ids[w.day_index],
            started_at=w.started_at,
            ended_at=w.ended_at,
            notes=w.notes,
            strava_activity_id=w.strava_activity_id,
        )
        session.add(workout)
        await session.flush()
        workout_ids[w.client_id] = workout.id
        session.add_all(
            WorkoutSet(
                user_id=user_id,
                client_id=s.client_id,
                workout_id=workout.id,
                exercise_id=exercise_ids[s.slug],
                set_index=s.set_index,
                reps=s.reps,
                weight_kg=s.weight_kg,
                rpe=s.rpe,
                completed_at=s.completed_at,
                rest_seconds=s.rest_seconds,
            )
            for s in w.sets
        )
    return workout_ids


async def _write_nutrition(session: AsyncSession, user_id: int, data: DemoDataset) -> None:
    session.add(
        NutritionProfile(
            user_id=user_id,
            sex=seed.PROFILE_SEX,
            birth_year=seed.PROFILE_BIRTH_YEAR,
            height_cm=seed.PROFILE_HEIGHT_CM,
            activity_baseline=seed.PROFILE_BASELINE,
            kcal_target=seed.PROFILE_KCAL_TARGET,
            protein_target_g=seed.PROFILE_PROTEIN_TARGET_G,
        )
    )
    foods = {
        f.name: Food(
            user_id=user_id,
            name=f.name,
            kcal_100g=f.kcal_100g,
            protein_100g=f.protein_100g,
            carbs_100g=f.carbs_100g,
            fat_100g=f.fat_100g,
        )
        for f in data.foods
    }
    session.add_all(foods.values())
    await session.flush()
    session.add_all(
        FoodFavorite(user_id=user_id, food_id=foods[f.name].id) for f in data.foods if f.favorite
    )
    session.add_all(
        FoodLog(
            user_id=user_id,
            client_id=log_.client_id,
            date=log_.date,
            meal=log_.meal,
            food_id=foods[log_.food].id,
            grams=log_.grams,
            kcal_100g=foods[log_.food].kcal_100g,
            protein_100g=foods[log_.food].protein_100g,
            carbs_100g=foods[log_.food].carbs_100g,
            fat_100g=foods[log_.food].fat_100g,
        )
        for log_ in data.food_logs
    )
