"""Deterministic fake athletes and activities."""

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

# Seeded history ends here, so the data does not depend on when the fake starts.
SEED_END = datetime(2026, 1, 1, tzinfo=UTC)
DEFAULT_ATHLETE_ID = 1001
FIRST_ACTIVITY_ID = 10_000_000_000
# Each athlete gets its own id range so ids never collide.
ACTIVITY_ID_STRIDE = 100_000_000

_FIRSTNAMES = ["Ada", "Kemal", "Lena", "Mateo", "Noor", "Sven"]
_LASTNAMES = ["Runner", "Rider", "Swimmer", "Climber"]

# sport_type, (min_km, max_km), (min, max) pace in s/km, elevation gain in m per km
_SPORTS: list[tuple[str, tuple[float, float], tuple[int, int], float]] = [
    ("Run", (4.0, 22.0), (270, 390), 8.0),
    ("Ride", (20.0, 110.0), (100, 160), 12.0),
    ("Swim", (1.0, 4.0), (110, 160), 0.0),
    ("Walk", (2.0, 8.0), (540, 720), 5.0),
    ("Hike", (6.0, 20.0), (600, 900), 45.0),
    ("TrailRun", (6.0, 30.0), (330, 480), 35.0),
]
_SPORT_WEIGHTS = [45, 25, 10, 8, 5, 7]


@dataclass
class FakeAthlete:
    id: int
    firstname: str
    lastname: str

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "firstname": self.firstname, "lastname": self.lastname}


@dataclass
class FakeActivity:
    id: int
    athlete_id: int
    name: str
    sport_type: str
    start_date: datetime
    distance: float
    moving_time: int
    elapsed_time: int
    total_elevation_gain: float
    average_heartrate: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "athlete": {"id": self.athlete_id},
            "name": self.name,
            "type": self.sport_type,
            "sport_type": self.sport_type,
            "start_date": format_ts(self.start_date),
            "distance": self.distance,
            "moving_time": self.moving_time,
            "elapsed_time": self.elapsed_time,
            "total_elevation_gain": self.total_elevation_gain,
        }
        if self.average_heartrate is not None:
            data["average_heartrate"] = self.average_heartrate
        data.update(self.extra)
        return data


def format_ts(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_athletes(count: int, rng_seed: int) -> list[FakeAthlete]:
    rng = random.Random(f"athletes:{rng_seed}")
    return [
        FakeAthlete(
            id=DEFAULT_ATHLETE_ID + i,
            firstname=rng.choice(_FIRSTNAMES),
            lastname=rng.choice(_LASTNAMES),
        )
        for i in range(count)
    ]


def first_activity_id(athlete_index: int) -> int:
    return FIRST_ACTIVITY_ID + athlete_index * ACTIVITY_ID_STRIDE


def seed_activities(
    athlete_id: int, count: int, rng_seed: int, first_id: int = FIRST_ACTIVITY_ID
) -> list[FakeActivity]:
    """`count` activities before SEED_END, oldest first; ids grow with start_date."""
    rng = random.Random(f"activities:{rng_seed}:{athlete_id}")
    starts: list[datetime] = []
    cursor = SEED_END
    for _ in range(count):
        cursor -= timedelta(minutes=rng.randint(8 * 60, 40 * 60))
        starts.append(cursor)
    starts.reverse()
    return [_make_activity(rng, athlete_id, first_id + i, start) for i, start in enumerate(starts)]


def _make_activity(
    rng: random.Random, athlete_id: int, activity_id: int, start: datetime
) -> FakeActivity:
    sport, (lo, hi), (pace_lo, pace_hi), elev_per_km = rng.choices(_SPORTS, weights=_SPORT_WEIGHTS)[
        0
    ]
    km = round(rng.uniform(lo, hi), 2)
    moving = int(km * rng.randint(pace_lo, pace_hi))
    heartrate = round(rng.uniform(118.0, 172.0), 1) if rng.random() < 0.7 else None
    return FakeActivity(
        id=activity_id,
        athlete_id=athlete_id,
        name=f"{_time_of_day(start)} {sport}",
        sport_type=sport,
        start_date=start,
        distance=round(km * 1000.0, 1),
        moving_time=moving,
        elapsed_time=moving + rng.randint(0, 900),
        total_elevation_gain=round(km * elev_per_km * rng.uniform(0.5, 1.5), 1),
        average_heartrate=heartrate,
    )


def _time_of_day(start: datetime) -> str:
    if start.hour < 12:
        return "Morning"
    if start.hour < 18:
        return "Afternoon"
    return "Evening"
