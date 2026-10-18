"""The demo dataset (P7.9, ADR 0028): synthetic, deterministic, built from code only.

Everything here comes from the constants in this module and one `random.Random(DEMO_RNG_SEED)`;
nothing is read from a file, the network or the environment (tests/unit/test_demo_seed.py checks
the source). `build_dataset(now, zone)` depends only on the local date of `now`, so the nightly
reset slides the same twelve weeks forward and the dashboard's default ranges always show data.

The athlete has no name: the data model stores none, and the demo invents none.
"""

import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from trainsync.strava.models import StravaActivity

DEMO_RNG_SEED = 7
WEEKS = 12
DEMO_STRAVA_ATHLETE_ID = 1001
FIRST_ACTIVITY_ID = 9_100_000_000

# ---------------------------------------------------------------- training

PROGRAM_NAME = "Upper/Lower 4-day"
PROGRAM_GOAL = "hypertrophy"


@dataclass(frozen=True, slots=True)
class PlannedExercise:
    slug: str  # an exercise of the seeded library (migration 0005)
    sets: int
    rep_min: int
    rep_max: int
    rest_seconds: int
    start_kg: Decimal
    step_kg: Decimal  # added roughly every other week


def _ex(slug: str, sets: int, reps: tuple[int, int], start: str, step: str) -> PlannedExercise:
    rest = 150 if reps[0] <= 6 else 90
    return PlannedExercise(slug, sets, reps[0], reps[1], rest, Decimal(start), Decimal(step))


# (day name, local weekday 0 = Monday, exercises)
PROGRAM_DAYS: tuple[tuple[str, int, tuple[PlannedExercise, ...]], ...] = (
    (
        "Upper A",
        0,
        (
            _ex("bench-press", 3, (6, 10), "60", "2.5"),
            _ex("barbell-row", 3, (8, 12), "50", "2.5"),
            _ex("overhead-press", 3, (6, 10), "35", "2.5"),
            _ex("lat-pulldown", 3, (10, 12), "45", "2.5"),
            _ex("dumbbell-curl", 2, (10, 15), "12", "1"),
        ),
    ),
    (
        "Lower A",
        1,
        (
            _ex("back-squat", 3, (6, 10), "70", "5"),
            _ex("romanian-deadlift", 3, (8, 12), "60", "5"),
            _ex("leg-press", 3, (10, 15), "120", "10"),
            _ex("leg-curl", 3, (10, 15), "35", "2.5"),
            _ex("standing-calf-raise", 3, (10, 15), "60", "5"),
        ),
    ),
    (
        "Upper B",
        3,
        (
            _ex("incline-dumbbell-press", 3, (8, 12), "22", "2"),
            _ex("pull-up", 3, (6, 10), "0", "0"),
            _ex("dumbbell-shoulder-press", 3, (8, 12), "18", "2"),
            _ex("seated-cable-row", 3, (10, 12), "50", "2.5"),
            _ex("triceps-pushdown", 2, (10, 15), "25", "2.5"),
        ),
    ),
    (
        "Lower B",
        4,
        (
            _ex("deadlift", 3, (5, 8), "100", "5"),
            _ex("bulgarian-split-squat", 3, (8, 12), "16", "2"),
            _ex("hip-thrust", 3, (8, 12), "80", "5"),
            _ex("leg-extension", 3, (10, 15), "40", "2.5"),
            _ex("hanging-leg-raise", 3, (10, 15), "0", "0"),
        ),
    ),
)
WORKOUT_LOCAL_START = time(18, 30)
WORKOUT_NOTES = ("", "", "", "Felt strong today.", "Short on time, kept rests tight.")
PARTIAL_NOTE = "Ran out of time."
SKIP_REASONS = ("Late meeting at work.", "Travel day.", "Slept badly, took it easy.")
SICK_REASON = "Head cold."

# ---------------------------------------------------------------- activities

# sport_type, (min, max) km, (min, max) s/km, elevation m/km, weekday chances (0 = Monday)
CARDIO: tuple[tuple[str, tuple[float, float], tuple[int, int], float, dict[int, float]], ...] = (
    ("Run", (5.0, 12.0), (290, 360), 6.0, {2: 0.8, 6: 0.3}),
    ("Ride", (30.0, 75.0), (110, 150), 10.0, {5: 0.75}),
    ("Walk", (3.0, 7.0), (560, 700), 4.0, {6: 0.5}),
    ("Hike", (8.0, 16.0), (650, 850), 40.0, {6: 0.15}),
)
CARDIO_LOCAL_START = time(7, 15)
WEIGHT_TRAINING = "WeightTraining"

# ---------------------------------------------------------------- nutrition

# name, kcal, protein, carbs, fat per 100 g; favourite
FOODS: tuple[tuple[str, str, str, str, str, bool], ...] = (
    ("Rolled oats", "379", "13.2", "67.7", "6.5", True),
    ("Whole milk", "61", "3.2", "4.8", "3.3", False),
    ("Banana", "89", "1.1", "22.8", "0.3", True),
    ("Eggs", "143", "12.6", "0.7", "9.5", True),
    ("Whole wheat bread", "247", "13.0", "41.0", "3.4", False),
    ("Chicken breast, cooked", "165", "31.0", "0.0", "3.6", True),
    ("White rice, cooked", "130", "2.7", "28.0", "0.3", True),
    ("Broccoli", "34", "2.8", "6.6", "0.4", False),
    ("Salmon, baked", "208", "20.0", "0.0", "13.0", False),
    ("Lentils, cooked", "116", "9.0", "20.0", "0.4", False),
    ("Olive oil", "884", "0.0", "0.0", "100.0", False),
    ("Greek yogurt", "97", "9.0", "3.9", "5.0", True),
    ("Peanut butter", "588", "25.0", "20.0", "50.0", False),
    ("Apple", "52", "0.3", "14.0", "0.2", False),
    ("Potatoes, boiled", "87", "1.9", "20.0", "0.1", False),
)
# meal -> alternative plates of (food name, typical grams)
MEALS: dict[str, tuple[tuple[tuple[str, int], ...], ...]] = {
    "breakfast": (
        (("Rolled oats", 80), ("Whole milk", 250), ("Banana", 120)),
        (("Eggs", 150), ("Whole wheat bread", 80)),
    ),
    "lunch": (
        (("Chicken breast, cooked", 180), ("White rice, cooked", 250), ("Broccoli", 150)),
        (("Lentils, cooked", 300), ("Whole wheat bread", 60)),
    ),
    "dinner": (
        (("Salmon, baked", 170), ("Potatoes, boiled", 300), ("Olive oil", 10)),
        (("Chicken breast, cooked", 200), ("White rice, cooked", 200), ("Olive oil", 10)),
    ),
    "snack": (
        (("Greek yogurt", 200), ("Apple", 150)),
        (("Peanut butter", 30), ("Banana", 120)),
    ),
}

# Profile: only what the energy estimate needs (ADR 0019); no name, no birth date.
PROFILE_SEX = "male"
PROFILE_BIRTH_YEAR = 1992
PROFILE_HEIGHT_CM = Decimal("180.0")
PROFILE_BASELINE = "light"
PROFILE_KCAL_TARGET = 2500
PROFILE_PROTEIN_TARGET_G = 160
WEIGHT_START_KG = 82.4
WEIGHT_END_KG = 79.8


# ---------------------------------------------------------------- dataset


@dataclass(frozen=True, slots=True)
class DemoSet:
    client_id: uuid.UUID
    slug: str
    set_index: int
    reps: int
    weight_kg: Decimal
    rpe: Decimal
    completed_at: datetime
    rest_seconds: int | None


@dataclass(frozen=True, slots=True)
class DemoWorkout:
    client_id: uuid.UUID
    day_index: int
    started_at: datetime
    ended_at: datetime
    notes: str
    partial: bool
    strava_activity_id: int
    sets: tuple[DemoSet, ...]


@dataclass(frozen=True, slots=True)
class DemoCheckin:
    date: date
    status: str
    workout: uuid.UUID | None  # client id of the day's workout
    reason_note: str | None
    sleep_hours: Decimal
    energy_1_5: int
    body_weight_kg: Decimal | None


@dataclass(frozen=True, slots=True)
class DemoFood:
    name: str
    kcal_100g: Decimal
    protein_100g: Decimal
    carbs_100g: Decimal
    fat_100g: Decimal
    favorite: bool


@dataclass(frozen=True, slots=True)
class DemoFoodLog:
    client_id: uuid.UUID
    date: date
    meal: str
    food: str
    grams: Decimal


@dataclass(slots=True)
class DemoDataset:
    today: date
    activities: list[StravaActivity] = field(default_factory=list)
    workouts: list[DemoWorkout] = field(default_factory=list)
    checkins: list[DemoCheckin] = field(default_factory=list)
    foods: list[DemoFood] = field(default_factory=list)
    food_logs: list[DemoFoodLog] = field(default_factory=list)
    body_weights: dict[date, Decimal] = field(default_factory=dict)


def build_dataset(now: datetime, zone: ZoneInfo) -> DemoDataset:
    """The twelve weeks before `now`'s local date in `zone` (today: breakfast only)."""
    rng = random.Random(DEMO_RNG_SEED)  # noqa: S311  (synthetic demo data, not security)
    today = now.astimezone(zone).date()
    first = today - timedelta(weeks=WEEKS)
    data = DemoDataset(today=today)
    data.foods = [_food(row) for row in FOODS]
    for offset in range((today - first).days):
        day = first + timedelta(days=offset)
        _build_day(rng, data, day, offset // 7, zone)
    data.food_logs += _meal(rng, today, "breakfast")
    # Nothing in the future, even when `now` is early in the day.
    data.activities = [a for a in data.activities if a.start_date <= now]
    return data


def _build_day(rng: random.Random, data: DemoDataset, day: date, week: int, zone: ZoneInfo) -> None:
    weight = _body_weight(rng, day, data.today)
    if rng.random() < 0.6:
        data.body_weights[day] = weight
    workout = _maybe_workout(rng, data, day, week, zone)
    cardio = _cardio(rng, data, day, zone)
    data.checkins.append(_checkin(rng, day, workout, cardio, data.body_weights.get(day)))
    if rng.random() < 0.93:  # a few days are never logged
        for meal in MEALS:
            if meal != "snack" or rng.random() < 0.7:
                data.food_logs += _meal(rng, day, meal)


def _body_weight(rng: random.Random, day: date, today: date) -> Decimal:
    progress = 1 - (today - day).days / (WEEKS * 7)
    trend = WEIGHT_START_KG + (WEIGHT_END_KG - WEIGHT_START_KG) * progress
    return Decimal(str(round(trend + rng.uniform(-0.4, 0.4), 1)))


def _uuid(rng: random.Random) -> uuid.UUID:
    return uuid.UUID(int=rng.getrandbits(128), version=4)


def _local(day: date, at: time, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, at, tzinfo=zone).astimezone(UTC)


def _next_activity_id(data: DemoDataset) -> int:
    return FIRST_ACTIVITY_ID + len(data.activities)


# ---------------------------------------------------------------- workouts


@dataclass(slots=True)
class _Missed:
    reason: str
    sick: bool


def _maybe_workout(
    rng: random.Random, data: DemoDataset, day: date, week: int, zone: ZoneInfo
) -> DemoWorkout | _Missed | None:
    planned = [i for i, (_, weekday, _) in enumerate(PROGRAM_DAYS) if weekday == day.weekday()]
    if not planned:
        return None
    roll = rng.random()
    if roll < 0.04:
        return _Missed(SICK_REASON, sick=True)
    if roll < 0.14:
        return _Missed(rng.choice(SKIP_REASONS), sick=False)
    day_index = planned[0]
    partial = rng.random() < 0.08
    workout = _workout(rng, data, day, day_index, week, partial, zone)
    data.workouts.append(workout)
    return workout


def _workout(
    rng: random.Random,
    data: DemoDataset,
    day: date,
    day_index: int,
    week: int,
    partial: bool,
    zone: ZoneInfo,
) -> DemoWorkout:
    started = _local(day, WORKOUT_LOCAL_START, zone) + timedelta(minutes=rng.randint(-20, 40))
    exercises = PROGRAM_DAYS[day_index][2]
    if partial:
        exercises = exercises[:2]
    sets: list[DemoSet] = []
    clock = started + timedelta(minutes=8)  # warm-up
    for planned in exercises:
        weight = _working_weight(rng, planned, week)
        for set_index in range(planned.sets):
            rest = None if set_index == 0 else planned.rest_seconds + rng.randint(-15, 45)
            clock += timedelta(seconds=(rest or 120) + 40)
            sets.append(_set(rng, planned, set_index, weight, clock, rest))
    ended = clock + timedelta(minutes=5)
    name = f"{_time_of_day(started.astimezone(zone))} Weight Training"
    activity = _weight_training(rng, data, name, started, ended)
    return DemoWorkout(
        client_id=_uuid(rng),
        day_index=day_index,
        started_at=started,
        ended_at=ended,
        notes=PARTIAL_NOTE if partial else rng.choice(WORKOUT_NOTES),
        partial=partial,
        strava_activity_id=activity.id,
        sets=tuple(sets),
    )


def _working_weight(rng: random.Random, planned: PlannedExercise, week: int) -> Decimal:
    steps = (week + rng.choice((0, 0, 1))) // 2
    return planned.start_kg + planned.step_kg * steps


def _set(
    rng: random.Random,
    planned: PlannedExercise,
    set_index: int,
    weight: Decimal,
    completed_at: datetime,
    rest: int | None,
) -> DemoSet:
    reps = max(planned.rep_min, planned.rep_max - set_index - rng.randint(0, 2))
    return DemoSet(
        client_id=_uuid(rng),
        slug=planned.slug,
        set_index=set_index,
        reps=reps,
        weight_kg=weight,
        rpe=Decimal(rng.choice(("7", "7.5", "8", "8.5", "9"))),
        completed_at=completed_at,
        rest_seconds=rest,
    )


def _weight_training(
    rng: random.Random, data: DemoDataset, name: str, started: datetime, ended: datetime
) -> StravaActivity:
    moving = int((ended - started).total_seconds())
    activity = StravaActivity(
        id=_next_activity_id(data),
        name=name,
        sport_type=WEIGHT_TRAINING,
        start_date=started,
        distance=0.0,
        moving_time=moving,
        elapsed_time=moving,
        total_elevation_gain=0.0,
        average_heartrate=round(rng.uniform(105.0, 128.0), 1),
    )
    data.activities.append(activity)
    return activity


# ---------------------------------------------------------------- cardio


def _cardio(rng: random.Random, data: DemoDataset, day: date, zone: ZoneInfo) -> bool:
    done = False
    for sport, (km_lo, km_hi), (pace_lo, pace_hi), elevation, chances in CARDIO:
        if rng.random() >= chances.get(day.weekday(), 0.0):
            continue
        start = _local(day, CARDIO_LOCAL_START, zone) + timedelta(minutes=rng.randint(0, 150))
        km = round(rng.uniform(km_lo, km_hi), 2)
        moving = int(km * rng.randint(pace_lo, pace_hi))
        data.activities.append(
            StravaActivity(
                id=_next_activity_id(data),
                name=f"{_time_of_day(start.astimezone(zone))} {sport}",
                sport_type=sport,
                start_date=start,
                distance=round(km * 1000.0, 1),
                moving_time=moving,
                elapsed_time=moving + rng.randint(0, 600),
                total_elevation_gain=round(km * elevation * rng.uniform(0.6, 1.4), 1),
                average_heartrate=round(rng.uniform(128.0, 162.0), 1),
            )
        )
        done = True
    return done


def _time_of_day(start: datetime) -> str:
    if start.hour < 12:
        return "Morning"
    if start.hour < 18:
        return "Afternoon"
    return "Evening"


# ---------------------------------------------------------------- check-ins and nutrition


def _checkin(
    rng: random.Random,
    day: date,
    workout: DemoWorkout | _Missed | None,
    cardio: bool,
    weight: Decimal | None,
) -> DemoCheckin:
    reason = None
    linked = None
    if isinstance(workout, DemoWorkout):
        status = "partial" if workout.partial else "done"
        linked = workout.client_id
    elif isinstance(workout, _Missed):
        status = "sick_or_injured" if workout.sick else "skipped"
        reason = workout.reason
    else:
        status = "done" if cardio else "rest"
    return DemoCheckin(
        date=day,
        status=status,
        workout=linked,
        reason_note=reason,
        sleep_hours=Decimal(str(rng.choice((6, 6.5, 7, 7, 7.5, 7.5, 8, 8.5)))),
        energy_1_5=2 if status == "sick_or_injured" else rng.choice((3, 3, 4, 4, 4, 5)),
        body_weight_kg=weight,
    )


def _food(row: tuple[str, str, str, str, str, bool]) -> DemoFood:
    name, kcal, protein, carbs, fat, favorite = row
    return DemoFood(name, Decimal(kcal), Decimal(protein), Decimal(carbs), Decimal(fat), favorite)


def _meal(rng: random.Random, day: date, meal: str) -> list[DemoFoodLog]:
    plate = rng.choice(MEALS[meal])
    return [
        DemoFoodLog(
            client_id=_uuid(rng),
            date=day,
            meal=meal,
            food=food,
            grams=Decimal(round(grams * rng.uniform(0.85, 1.15))),
        )
        for food, grams in plate
    ]
