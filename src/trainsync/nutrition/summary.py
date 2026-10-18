"""Daily nutrition and energy-balance summaries from the database (ADR 0019).

Days are UTC calendar days, like the rest of the read API: an activity belongs to the day of its
UTC `start_date`, a food log to the `date` the client sent.
"""

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.db.models import Activity, ActivityBaseline, BodyMetric, NutritionProfile, Sex
from trainsync.db.repositories.nutrition import NutritionRepository
from trainsync.db.repositories.reads import ActivityFilter, ReadRepository
from trainsync.db.repositories.training import BodyMetricRepository
from trainsync.nutrition.energy import (
    ActivityEnergy,
    Balance,
    Intake,
    IntakeEntry,
    activity_kcal,
    age_on,
    balance,
    baseline_kcal,
    bmr_mifflin_st_jeor,
    intake,
)


class EstimateGap(StrEnum):
    """Why BMR and the everyday baseline could not be estimated for a day."""

    NO_PROFILE = "no_profile"
    NO_BODY_WEIGHT = "no_body_weight"


@dataclass(frozen=True, slots=True)
class Bmr:
    bmr: Decimal | None
    weight: BodyMetric | None
    gap: EstimateGap | None


@dataclass(frozen=True, slots=True)
class DayEnergy:
    day: date
    intake: Intake
    profile: NutritionProfile | None
    bmr: Bmr
    baseline_kcal: Decimal | None
    activities: list[tuple[Activity, ActivityEnergy]]
    balance: Balance


def days(start: date, end: date) -> Iterator[date]:
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def utc_midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def estimate_bmr(profile: NutritionProfile | None, weight: BodyMetric | None, day: date) -> Bmr:
    """BMR for `day` from the profile and the given body weight, or the reason it is missing."""
    if profile is None:
        return Bmr(None, weight, EstimateGap.NO_PROFILE)
    if weight is None:
        return Bmr(None, None, EstimateGap.NO_BODY_WEIGHT)
    bmr = bmr_mifflin_st_jeor(
        Sex(profile.sex), weight.weight_kg, profile.height_cm, age_on(profile.birth_year, day)
    )
    return Bmr(bmr, weight, None)


async def latest_weight(session: AsyncSession, day: date) -> BodyMetric | None:
    return await BodyMetricRepository(session).latest(on_or_before=day)


async def energy_days(session: AsyncSession, start: date, end: date) -> list[DayEnergy]:
    """One `DayEnergy` per UTC day in `start`..`end` (inclusive), zero-filled."""
    repo = NutritionRepository(session)
    profile = await repo.profile()

    entries: dict[date, list[IntakeEntry]] = defaultdict(list)
    for log, _ in await repo.log_entries(start, end):
        # The values snapshotted at log time, not the food's current ones.
        entries[log.date].append(
            IntakeEntry(
                log.grams,
                log.kcal_100g,
                log.protein_100g,
                log.carbs_100g,
                log.fat_100g,
                log.sugars_100g,
            )
        )

    athlete_ids = await ReadRepository(session).active_athlete_ids()
    activity_filter = ActivityFilter(
        athlete_ids, utc_midnight(start), utc_midnight(end + timedelta(days=1))
    )
    activities: dict[date, list[tuple[Activity, ActivityEnergy]]] = defaultdict(list)
    for activity in await repo.activities(activity_filter):
        energy = activity_kcal(activity.sport_type, activity.raw)
        activities[activity.start_date.astimezone(UTC).date()].append((activity, energy))

    metrics = BodyMetricRepository(session)
    weights = {m.date: m for m in await metrics.between(start, end)}
    weight = await metrics.latest(on_or_before=start)

    result = []
    for day in days(start, end):
        weight = weights.get(day, weight)
        day_intake = intake(entries.get(day, []))
        bmr = estimate_bmr(profile, weight, day)
        baseline = (
            baseline_kcal(bmr.bmr, ActivityBaseline(profile.activity_baseline))
            if bmr.bmr is not None and profile is not None
            else None
        )
        day_activities = activities.get(day, [])
        day_balance = balance(day_intake.kcal, baseline, [e for _, e in day_activities])
        result.append(
            DayEnergy(day, day_intake, profile, bmr, baseline, day_activities, day_balance)
        )
    return result
