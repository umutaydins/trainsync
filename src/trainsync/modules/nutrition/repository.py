"""Nutrition tables: foods (with the Open Food Facts cache), food logs, profile (Phase 6)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, case, delete, func, literal_column, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.integrations.openfoodfacts.client import OffProduct
from trainsync.modules.activities.models import Activity
from trainsync.modules.activities.reads import ActivityFilter
from trainsync.modules.nutrition.models import Food, FoodLog, FoodSource, Meal, NutritionProfile
from trainsync.modules.nutrition.sugar import food_group_from_categories

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


class NutritionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------ foods

    async def food(self, food_id: int) -> Food | None:
        return await self._session.get(Food, food_id)

    async def food_by_barcode(self, barcode: str) -> Food | None:
        return await self._session.scalar(select(Food).where(Food.barcode == barcode))

    async def search_foods(
        self, q: str | None = None, *, favorites_only: bool = False, limit: int = 50
    ) -> list[Food]:
        """Case-insensitive substring of name or brand; favorites first, then by name."""
        stmt = select(Food).order_by(Food.favorite.desc(), func.lower(Food.name), Food.id)
        if q and q.strip():
            needle = q.strip().lower()
            stmt = stmt.where(
                or_(
                    func.lower(Food.name).contains(needle, autoescape=True),
                    func.lower(Food.brand).contains(needle, autoescape=True),
                    Food.barcode == q.strip(),
                )
            )
        if favorites_only:
            stmt = stmt.where(Food.favorite)
        return list(await self._session.scalars(stmt.limit(limit)))

    async def add_food(self, food: Food) -> Food:
        self._session.add(food)
        await self._session.flush()
        await self._session.refresh(food)
        return food

    async def set_favorite(self, food_id: int, favorite: bool) -> Food | None:
        await self._session.execute(
            update(Food).where(Food.id == food_id).values(favorite=favorite)
        )
        return await self._fresh(food_id)

    async def cache_products(self, products: Sequence[OffProduct]) -> list[Food]:
        """Upsert Open Food Facts products by barcode. A row the user edited (now `manual`)
        keeps its values; `favorite` is never touched. Returns the stored rows."""
        unique = {p.barcode: p for p in products}
        if not unique:
            return []
        rows = [
            {
                "barcode": p.barcode,
                "name": p.name,
                "brand": p.brand,
                "kcal_100g": p.kcal_100g,
                "protein_100g": p.protein_100g,
                "carbs_100g": p.carbs_100g,
                "fat_100g": p.fat_100g,
                "sugars_100g": p.sugars_100g,
                "nova_group": p.nova_group,
                "food_group": food_group_from_categories(p.categories),
                "source": FoodSource.OPENFOODFACTS.value,
            }
            for p in unique.values()
        ]
        stmt = insert(Food).values(rows)
        fields = (
            "name",
            "brand",
            "kcal_100g",
            "protein_100g",
            "carbs_100g",
            "fat_100g",
            "sugars_100g",
            "nova_group",
            "food_group",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Food.barcode],
            set_={name: stmt.excluded[name] for name in fields},
            where=Food.source == FoodSource.OPENFOODFACTS.value,
        )
        await self._session.execute(stmt)
        stored = await self._session.scalars(
            select(Food).where(Food.barcode.in_(unique)).execution_options(populate_existing=True)
        )
        by_barcode = {f.barcode: f for f in stored}
        return [by_barcode[b] for b in unique if b in by_barcode]

    async def _fresh(self, food_id: int) -> Food | None:
        return await self._session.scalar(
            select(Food).where(Food.id == food_id).execution_options(populate_existing=True)
        )

    # ------------------------------------------------------------ food log

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
        values_stmt = insert(FoodLog).values(client_id=client_id, **fields)
        stmt = values_stmt.on_conflict_do_update(
            index_elements=[FoodLog.client_id],
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
            delete(FoodLog).where(FoodLog.client_id == client_id).returning(FoodLog.id)
        )
        return result.scalar_one_or_none() is not None

    async def log_entries(self, start: date, end: date) -> list[tuple[FoodLog, Food]]:
        """Entries with their food for the days `start`..`end` (inclusive), in day and meal
        order, then as logged."""
        stmt = (
            select(FoodLog, Food)
            .join(Food, Food.id == FoodLog.food_id)
            .where(FoodLog.date >= start, FoodLog.date <= end)
            .order_by(FoodLog.date, MEAL_ORDER, FoodLog.created_at, FoodLog.id)
        )
        result = await self._session.execute(stmt)
        return [(log, food) for log, food in result.tuples()]

    # ------------------------------------------------------------ profile

    async def profile(self) -> NutritionProfile | None:
        return await self._session.get(NutritionProfile, 1)

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
        stmt = insert(NutritionProfile).values(id=1, **fields)
        stmt = stmt.on_conflict_do_update(
            index_elements=[NutritionProfile.id], set_={k: stmt.excluded[k] for k in fields}
        )
        await self._session.execute(stmt)
        stored = await self._session.scalar(
            select(NutritionProfile)
            .where(NutritionProfile.id == 1)
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
            .where(*activity_filter.conditions())
            .order_by(Activity.start_date, Activity.id)
        )
        return list(await self._session.scalars(stmt))
