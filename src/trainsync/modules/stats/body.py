"""Body statistics: weight trend, its 7-day moving average and rate per week (P8.10).

The moving average of a day is the mean of the weights logged in the 7 days ending that day
(fewer when days are missing). The rate is the least-squares slope of the window's weights per
day, times 7. Body fat arrives in Phase 9 (`body_fat_pct` stays None until then).
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.stats.periods import Window
from trainsync.modules.stats.scope import Scope
from trainsync.modules.training.models import BodyMetric

MOVING_AVERAGE_DAYS = 7
DAYS_PER_WEEK = 7


@dataclass(frozen=True, slots=True)
class WeightPoint:
    day: date
    weight_kg: float
    moving_average_kg: float


@dataclass(frozen=True, slots=True)
class Body:
    points: list[WeightPoint]
    rate_kg_per_week: float | None
    body_fat_pct: float | None = None

    @property
    def first_kg(self) -> float | None:
        return self.points[0].weight_kg if self.points else None

    @property
    def last_kg(self) -> float | None:
        return self.points[-1].weight_kg if self.points else None

    @property
    def change_kg(self) -> float | None:
        if self.first_kg is None or self.last_kg is None:
            return None
        return self.last_kg - self.first_kg


def moving_averages(weights: dict[date, float]) -> dict[date, float]:
    """The moving average of every logged day, in one pass over the days in order."""
    days = sorted(weights)
    averages: dict[date, float] = {}
    first, total = 0, 0.0
    for last, day in enumerate(days):
        total += weights[day]
        while days[first] < day - timedelta(MOVING_AVERAGE_DAYS - 1):
            total -= weights[days[first]]
            first += 1
        averages[day] = total / (last - first + 1)
    return averages


def slope_per_week(points: list[tuple[date, float]]) -> float | None:
    """Least-squares kg per day x 7; None with fewer than two days."""
    if len({d for d, _ in points}) < 2:
        return None
    origin = points[0][0]
    xs = [float((d - origin).days) for d, _ in points]
    ys = [w for _, w in points]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    denominator = sum((x - mean_x) ** 2 for x in xs)
    return numerator / denominator * DAYS_PER_WEEK


async def weights(session: AsyncSession, scope: Scope, start: date, end: date) -> dict[date, float]:
    rows = await session.execute(
        select(BodyMetric.date, BodyMetric.weight_kg)
        .where(
            BodyMetric.user_id == scope.user_id, BodyMetric.date >= start, BodyMetric.date <= end
        )
        .order_by(BodyMetric.date)
    )
    return {day: float(weight) for day, weight in rows.all()}


async def body(session: AsyncSession, scope: Scope, window: Window) -> Body:
    lead_in = window.start - timedelta(MOVING_AVERAGE_DAYS - 1)
    logged = await weights(session, scope, lead_in, window.end)
    inside = [(d, w) for d, w in logged.items() if d in window]
    averages = moving_averages(logged)
    points = [WeightPoint(d, w, averages[d]) for d, w in inside]
    return Body(points, slope_per_week(inside))
