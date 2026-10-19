"""Nutrition statistics from the food log (P8.10, ADR 0038).

One query sums each local day per food group and NOVA group; the free-sugar rule of the coach
(`nutrition.sugar.counts_as_free_sugar`) then decides which sugar counts toward the limit.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.nutrition.models import FoodLog, NutritionProfile
from trainsync.modules.nutrition.sugar import counts_as_free_sugar
from trainsync.modules.stats.periods import Window
from trainsync.modules.stats.scope import Scope

PER_100G = 100


@dataclass(slots=True)
class Day:
    kcal: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    free_sugars_g: float = 0.0


@dataclass(frozen=True, slots=True)
class Nutrition:
    days: dict[date, Day]
    window_days: int
    kcal_target: int | None
    sugar_limit_g: float

    def _mean(self, values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    @property
    def logged_days(self) -> int:
        return len(self.days)

    @property
    def avg_kcal(self) -> float | None:
        return self._mean([d.kcal for d in self.days.values()])

    @property
    def avg_protein_g(self) -> float | None:
        return self._mean([d.protein_g for d in self.days.values()])

    @property
    def avg_carbs_g(self) -> float | None:
        return self._mean([d.carbs_g for d in self.days.values()])

    @property
    def avg_fat_g(self) -> float | None:
        return self._mean([d.fat_g for d in self.days.values()])

    @property
    def days_over_sugar_limit(self) -> int:
        return sum(1 for d in self.days.values() if d.free_sugars_g > self.sugar_limit_g)

    @property
    def logging_rate(self) -> float | None:
        return self.logged_days / self.window_days if self.window_days else None


def _amount(per_100g: ColumnElement[Any] | Any) -> ColumnElement[Any]:
    return func.coalesce(func.sum(FoodLog.grams * per_100g / PER_100G), 0)


async def daily(session: AsyncSession, scope: Scope, window: Window) -> dict[date, Day]:
    stmt = (
        select(
            FoodLog.date,
            FoodLog.food_group,
            FoodLog.nova_group,
            _amount(FoodLog.kcal_100g),
            _amount(FoodLog.protein_100g),
            _amount(FoodLog.carbs_100g),
            _amount(FoodLog.fat_100g),
            _amount(FoodLog.sugars_100g),
        )
        .where(
            FoodLog.user_id == scope.user_id,
            FoodLog.date >= window.start,
            FoodLog.date <= window.end,
        )
        .group_by(FoodLog.date, FoodLog.food_group, FoodLog.nova_group)
    )
    days: dict[date, Day] = defaultdict(Day)
    for day, group, nova, kcal, protein, carbs, fat, sugars in (await session.execute(stmt)).all():
        totals = days[day]
        totals.kcal += float(kcal)
        totals.protein_g += float(protein)
        totals.carbs_g += float(carbs)
        totals.fat_g += float(fat)
        if counts_as_free_sugar(group, nova):
            totals.free_sugars_g += float(Decimal(sugars))
    return dict(sorted(days.items()))


async def kcal_target(session: AsyncSession, user_id: int) -> int | None:
    return await session.scalar(
        select(NutritionProfile.kcal_target).where(NutritionProfile.user_id == user_id)
    )


async def nutrition(
    session: AsyncSession, scope: Scope, window: Window, sugar_limit_g: float
) -> Nutrition:
    return Nutrition(
        await daily(session, scope, window),
        window.days,
        await kcal_target(session, scope.user_id),
        sugar_limit_g,
    )
