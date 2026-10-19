"""Nutrition tables: foods (with the Open Food Facts cache), food logs, profile (Phase 6).

Bound to one user (ADR 0035): the user sees the shared catalogue (`user_id` null: the Open Food
Facts cache and what the owner curates) plus their own manual foods; favourites, logs and the
profile are theirs alone.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, case, delete, literal_column, select
from sqlalchemy.dialects.postgresql import insert

from trainsync.modules.activities.models import Activity
from trainsync.modules.activities.reads import ActivityFilter
from trainsync.modules.nutrition.food_repository import FoodRepository, FoodView
from trainsync.modules.nutrition.models import Food, FoodLog, Meal, NutritionProfile

__all__ = ["FoodView", "LogValues", "NutritionRepository", "ProfileValues"]

MEAL_ORDER = case({m.value: i for i, m in enumerate(Meal)}, value=FoodLog.meal)


@dataclass(frozen=True, slots=True)
class LogValues:
    date: date
    meal: str
    food: Food  # its current per-100 g values are snapshotted into the entry
    grams: Decimal


@dataclass(frozen=True, slots=True)
class ProfileValues:
    sex: str
    birth_year: int
    height_cm: Decimal
    activity_baseline: str
    kcal_target: int | None = None
    protein_target_g: int | None = None


class NutritionRepository(FoodRepository):
    """Foods and favourites (`FoodRepository`), plus the user's food log, profile and the
    activities the energy balance reads."""

    async def put_log(self, client_id: uuid.UUID, values: LogValues) -> tuple[FoodLog, bool]:
        """Idempotent upsert by `client_id`: (row, created). A retry updates the same row and
        takes a fresh snapshot of the food's values."""
        food = values.food
        fields = {
            "date": values.date,
            "meal": values.meal,
            "food_id": food.id,
            "grams": values.grams,
            "kcal_100g": food.kcal_100g,
            "protein_100g": food.protein_100g,
            "carbs_100g": food.carbs_100g,
            "fat_100g": food.fat_100g,
            "sugars_100g": food.sugars_100g,
            "nova_group": food.nova_group,
            "food_group": food.food_group,
        }
        values_stmt = insert(FoodLog).values(user_id=self._user_id, client_id=client_id, **fields)
        stmt = values_stmt.on_conflict_do_update(
            index_elements=[FoodLog.user_id, FoodLog.client_id],
            set_={name: values_stmt.excluded[name] for name in fields},
        ).returning(FoodLog.id, literal_column("xmax = 0", Boolean()).label("created"))
        row = (await self._session.execute(stmt)).one()
        stored = await self._session.scalar(
            select(FoodLog).where(FoodLog.id == row.id).execution_options(populate_existing=True)
        )
        if stored is None:  # pragma: no cover - just returned by the upsert
            raise LookupError(row.id)
        return stored, bool(row.created)

    async def delete_log(self, client_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(FoodLog)
            .where(FoodLog.user_id == self._user_id, FoodLog.client_id == client_id)
            .returning(FoodLog.id)
        )
        return result.scalar_one_or_none() is not None

    async def log_entries(self, start: date, end: date) -> list[tuple[FoodLog, Food]]:
        """Entries with their food for the days `start`..`end` (inclusive), in day and meal
        order, then as logged."""
        stmt = (
            select(FoodLog, Food)
            .join(Food, Food.id == FoodLog.food_id)
            .where(FoodLog.user_id == self._user_id, FoodLog.date >= start, FoodLog.date <= end)
            .order_by(FoodLog.date, MEAL_ORDER, FoodLog.created_at, FoodLog.id)
        )
        result = await self._session.execute(stmt)
        return [(log, food) for log, food in result.tuples()]

    # ------------------------------------------------------------ profile

    async def profile(self) -> NutritionProfile | None:
        return await self._session.get(NutritionProfile, self._user_id)

    async def put_profile(self, values: ProfileValues, now: datetime) -> NutritionProfile:
        fields = {
            "sex": values.sex,
            "birth_year": values.birth_year,
            "height_cm": values.height_cm,
            "activity_baseline": values.activity_baseline,
            "kcal_target": values.kcal_target,
            "protein_target_g": values.protein_target_g,
            "updated_at": now,
        }
        stmt = insert(NutritionProfile).values(user_id=self._user_id, **fields)
        stmt = stmt.on_conflict_do_update(
            index_elements=[NutritionProfile.user_id], set_={k: stmt.excluded[k] for k in fields}
        )
        await self._session.execute(stmt)
        stored = await self._session.scalar(
            select(NutritionProfile)
            .where(NutritionProfile.user_id == self._user_id)
            .execution_options(populate_existing=True)
        )
        if stored is None:  # pragma: no cover - just upserted
            raise LookupError("nutrition_profile")
        return stored

    # ------------------------------------------------------------ activities

    async def activities(self, activity_filter: ActivityFilter) -> list[Activity]:
        """Non-deleted activities matching the filter, oldest first."""
        stmt = (
            select(Activity)
            .where(Activity.user_id == self._user_id, *activity_filter.conditions())
            .order_by(Activity.start_date, Activity.id)
        )
        return list(await self._session.scalars(stmt))
