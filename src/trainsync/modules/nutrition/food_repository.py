"""The food catalogue as one user sees it: the shared foods (the Open Food Facts cache and what
the owner curates) plus their own manual foods, with their favourites (ADR 0035)."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, delete, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.integrations.openfoodfacts.client import OffProduct
from trainsync.modules.nutrition.models import Food, FoodFavorite, FoodSource
from trainsync.modules.nutrition.sugar import food_group_from_categories


@dataclass(frozen=True, slots=True)
class FoodView:
    """A food as one user sees it: with their favourite flag."""

    food: Food
    favorite: bool


class FoodRepository:
    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    def _visible(self) -> ColumnElement[bool]:
        return or_(Food.user_id.is_(None), Food.user_id == self._user_id)

    def _is_favorite(self) -> ColumnElement[bool]:
        return exists().where(
            FoodFavorite.user_id == self._user_id, FoodFavorite.food_id == Food.id
        )

    async def food(self, food_id: int) -> Food | None:
        return await self._session.scalar(select(Food).where(Food.id == food_id, self._visible()))

    async def food_by_barcode(self, barcode: str) -> Food | None:
        """The user's own food with this barcode first, else the shared one."""
        return await self._session.scalar(
            select(Food)
            .where(Food.barcode == barcode, self._visible())
            .order_by(Food.user_id.nulls_last())
            .limit(1)
        )

    async def views(self, foods: Sequence[Food]) -> list[FoodView]:
        ids = [f.id for f in foods]
        favorites = set(
            await self._session.scalars(
                select(FoodFavorite.food_id).where(
                    FoodFavorite.user_id == self._user_id, FoodFavorite.food_id.in_(ids)
                )
            )
        )
        return [FoodView(f, f.id in favorites) for f in foods]

    async def search_foods(
        self, q: str | None = None, *, favorites_only: bool = False, limit: int = 50
    ) -> list[FoodView]:
        """Case-insensitive substring of name or brand; favorites first, then by name."""
        favorite = self._is_favorite()
        stmt = (
            select(Food, favorite.label("favorite"))
            .where(self._visible())
            .order_by(favorite.desc(), func.lower(Food.name), Food.id)
        )
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
            stmt = stmt.where(favorite)
        rows = await self._session.execute(stmt.limit(limit))
        return [FoodView(food, bool(fav)) for food, fav in rows.tuples()]

    async def add_food(self, food: Food, *, favorite: bool = False) -> FoodView:
        """A manual food of this user (private to them)."""
        food.user_id = self._user_id
        self._session.add(food)
        await self._session.flush()
        await self._session.refresh(food)
        if favorite:
            await self._session.execute(
                insert(FoodFavorite).values(user_id=self._user_id, food_id=food.id)
            )
        return FoodView(food, favorite)

    async def set_favorite(self, food_id: int, favorite: bool) -> FoodView | None:
        food = await self.food(food_id)
        if food is None:
            return None
        if favorite:
            await self._session.execute(
                insert(FoodFavorite)
                .values(user_id=self._user_id, food_id=food_id)
                .on_conflict_do_nothing()
            )
        else:
            await self._session.execute(
                delete(FoodFavorite).where(
                    FoodFavorite.user_id == self._user_id, FoodFavorite.food_id == food_id
                )
            )
        return FoodView(food, favorite)

    async def cache_products(self, products: Sequence[OffProduct]) -> list[Food]:
        """Upsert Open Food Facts products into the shared catalogue by barcode. A shared row
        the owner edited (now `manual`) keeps its values. Returns the stored rows."""
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
            index_where=Food.user_id.is_(None),
            set_={name: stmt.excluded[name] for name in fields},
            where=Food.source == FoodSource.OPENFOODFACTS.value,
        )
        await self._session.execute(stmt)
        stored = await self._session.scalars(
            select(Food)
            .where(Food.barcode.in_(unique), Food.user_id.is_(None))
            .execution_options(populate_existing=True)
        )
        by_barcode = {f.barcode: f for f in stored}
        return [by_barcode[b] for b in unique if b in by_barcode]

    # ------------------------------------------------------------ food log
