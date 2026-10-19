"""Endurance statistics from synced activities, per sport group (P8.10, ADR 0038)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ColumnElement, Float, case, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.activities.models import Activity
from trainsync.modules.stats.periods import Window
from trainsync.modules.stats.scope import Scope


class SportGroup(StrEnum):
    RUN = "run"
    RIDE = "ride"
    WALK = "walk"
    SWIM = "swim"
    OTHER = "other"


SPORT_GROUPS: dict[str, SportGroup] = {
    **dict.fromkeys(("Run", "TrailRun", "VirtualRun"), SportGroup.RUN),
    **dict.fromkeys(
        (
            "Ride",
            "VirtualRide",
            "MountainBikeRide",
            "GravelRide",
            "EBikeRide",
            "EMountainBikeRide",
            "Velomobile",
            "Handcycle",
        ),
        SportGroup.RIDE,
    ),
    **dict.fromkeys(("Walk", "Hike"), SportGroup.WALK),
    "Swim": SportGroup.SWIM,
}
# "Fastest" ignores efforts too short to mean anything (a GPS blip, a 50 m sprint to the bus).
FASTEST_MIN_DISTANCE_M: dict[SportGroup, float] = {
    SportGroup.RUN: 1000,
    SportGroup.RIDE: 5000,
    SportGroup.WALK: 1000,
    SportGroup.SWIM: 100,
    SportGroup.OTHER: 1000,
}


@dataclass(frozen=True, slots=True)
class GroupTotals:
    group: SportGroup
    count: int
    distance_m: float
    moving_time_s: int
    elevation_gain_m: float
    # Average heart rate weighted by moving time, over the activities that have one.
    heartrate_time_s: int
    heartrate_weighted: float

    @property
    def average_speed_mps(self) -> float | None:
        return self.distance_m / self.moving_time_s if self.moving_time_s else None

    @property
    def average_heartrate(self) -> float | None:
        return self.heartrate_weighted / self.heartrate_time_s if self.heartrate_time_s else None


@dataclass(frozen=True, slots=True)
class Effort:
    group: SportGroup
    activity_id: int
    name: str
    start_date: datetime
    distance_m: float
    moving_time_s: int

    @property
    def average_speed_mps(self) -> float | None:
        return self.distance_m / self.moving_time_s if self.moving_time_s else None


@dataclass(frozen=True, slots=True)
class Endurance:
    groups: list[GroupTotals]
    longest: list[Effort]
    fastest: list[Effort]

    def total(self) -> GroupTotals:
        """All groups together (`group` is `other` and means nothing here)."""
        return GroupTotals(
            SportGroup.OTHER,
            sum(g.count for g in self.groups),
            sum(g.distance_m for g in self.groups),
            sum(g.moving_time_s for g in self.groups),
            sum(g.elevation_gain_m for g in self.groups),
            sum(g.heartrate_time_s for g in self.groups),
            sum(g.heartrate_weighted for g in self.groups),
        )


def group_column() -> ColumnElement[str]:
    groups: dict[SportGroup, list[str]] = {}
    for sport_type, group in SPORT_GROUPS.items():
        groups.setdefault(group, []).append(sport_type)
    return case(
        *[(Activity.sport_type.in_(types), literal(g.value)) for g, types in groups.items()],
        else_=literal(SportGroup.OTHER.value),
    )


def activity_conditions(scope: Scope, window: Window) -> list[ColumnElement[bool]]:
    start, end = window.bounds(scope.zone)
    return [
        Activity.user_id == scope.user_id,
        Activity.athlete_id.in_(scope.athlete_ids),
        Activity.deleted_at.is_(None),
        Activity.start_date >= start,
        Activity.start_date < end,
    ]


async def group_totals(session: AsyncSession, scope: Scope, window: Window) -> list[GroupTotals]:
    group = group_column().label("group")
    has_hr = Activity.average_heartrate.is_not(None)
    stmt = (
        select(
            group,
            func.count(),
            func.coalesce(func.sum(Activity.distance_m), 0.0),
            func.coalesce(func.sum(Activity.moving_time_s), 0),
            func.coalesce(func.sum(Activity.elevation_gain_m), 0.0),
            func.coalesce(func.sum(Activity.moving_time_s).filter(has_hr), 0),
            func.coalesce(
                func.sum(Activity.average_heartrate * Activity.moving_time_s).filter(has_hr), 0.0
            ),
        )
        .where(*activity_conditions(scope, window))
        .group_by(group)
        .order_by(group)
    )
    rows = (await session.execute(stmt)).all()
    return [
        GroupTotals(
            SportGroup(r[0]), r[1], float(r[2]), int(r[3]), float(r[4]), int(r[5]), float(r[6] or 0)
        )
        for r in rows
    ]


async def _efforts(
    session: AsyncSession, conditions: Sequence[ColumnElement[bool]], order: ColumnElement[Any]
) -> list[Effort]:
    group = group_column().label("group")
    stmt = (
        select(
            group,
            Activity.id,
            Activity.name,
            Activity.start_date,
            Activity.distance_m,
            Activity.moving_time_s,
        )
        .where(*conditions)
        .distinct(group)
        .order_by(group, order, Activity.start_date.desc(), Activity.id.desc())
    )
    return [Effort(SportGroup(r[0]), *r[1:]) for r in (await session.execute(stmt)).all()]


async def endurance(session: AsyncSession, scope: Scope, window: Window) -> Endurance:
    """Three queries: totals per group, the longest and the fastest effort per group."""
    conditions = activity_conditions(scope, window)
    min_distance = case(
        *[(group_column() == g.value, m) for g, m in FASTEST_MIN_DISTANCE_M.items()],
    )
    speed = Activity.distance_m / cast(func.nullif(Activity.moving_time_s, 0), Float)
    fastest_conditions = [
        *conditions,
        Activity.moving_time_s > 0,
        Activity.distance_m >= min_distance,
    ]
    return Endurance(
        groups=await group_totals(session, scope, window),
        longest=await _efforts(session, conditions, Activity.distance_m.desc()),
        fastest=await _efforts(session, fastest_conditions, speed.desc()),
    )
