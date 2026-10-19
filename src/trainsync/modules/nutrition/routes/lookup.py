"""`/v1/nutrition/foods/lookup`: Open Food Facts by barcode or text, cached in the food list."""

from typing import Annotated

from fastapi import HTTPException, Query, status

from trainsync.core.deps import SessionmakerDep
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.integrations.openfoodfacts.client import (
    OffProduct,
    OpenFoodFactsClient,
    OpenFoodFactsUnavailableError,
)
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.nutrition.repository import FoodView, NutritionRepository
from trainsync.modules.nutrition.routes.common import OpenFoodFactsDep, nutrition_router
from trainsync.modules.nutrition.schemas import FoodLookup, FoodOut, RemoteStatus
from trainsync.modules.nutrition.schemas.common import BARCODE_PATTERN

router = nutrition_router()

MIN_QUERY_LENGTH, MAX_QUERY_LENGTH = 2, 100
DEFAULT_LOOKUP_LIMIT, MAX_LOOKUP_LIMIT = 20, 50


@router.get(
    "/foods/lookup",
    summary="Look a food up in Open Food Facts",
    description=(
        "Exactly one of `barcode` or `q`. A barcode already stored is answered locally "
        "(`remote=cached`). Otherwise Open Food Facts is asked (3 s budget) and every usable "
        "product (barcode, name and kcal known) is cached in the food list. If Open Food Facts "
        "is slow or down the answer still comes, with local matches only and "
        "`remote=unavailable`."
    ),
    response_model=FoodLookup,
    responses={**UNAUTHORIZED, 400: error("Neither or both of barcode and q", "pass barcode or q")},
)
async def lookup_food(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    openfoodfacts: OpenFoodFactsDep,
    barcode: Annotated[
        str | None, Query(pattern=BARCODE_PATTERN, examples=["8690000000017"])
    ] = None,
    q: Annotated[
        str | None,
        Query(min_length=MIN_QUERY_LENGTH, max_length=MAX_QUERY_LENGTH, examples=["oats"]),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LOOKUP_LIMIT)] = DEFAULT_LOOKUP_LIMIT,
) -> FoodLookup:
    if (barcode is None) == (q is None):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "pass barcode or q")
    if barcode is not None:
        return await _lookup_barcode(sessionmaker, principal.user_id, openfoodfacts, barcode)
    return await _lookup_query(sessionmaker, principal.user_id, openfoodfacts, q or "", limit)


async def _lookup_barcode(
    sessionmaker: SessionmakerDep,
    user_id: int,
    openfoodfacts: OpenFoodFactsClient,
    barcode: str,
) -> FoodLookup:
    async with sessionmaker() as session:
        repo = NutritionRepository(session, user_id)
        local = await repo.food_by_barcode(barcode)
        views = await repo.views([local]) if local is not None else []
    if views:
        return FoodLookup(items=[FoodOut.from_view(v) for v in views], remote="cached")
    if not openfoodfacts.enabled:
        return FoodLookup(items=[], remote="disabled")
    try:
        product = await openfoodfacts.product(barcode)
    except OpenFoodFactsUnavailableError:
        return FoodLookup(items=[], remote="unavailable")
    if product is None:
        return FoodLookup(items=[], remote="not_found")
    rows = await _cache(sessionmaker, user_id, [product])
    return FoodLookup(items=[FoodOut.from_view(r) for r in rows], remote="ok")


async def _lookup_query(
    sessionmaker: SessionmakerDep,
    user_id: int,
    openfoodfacts: OpenFoodFactsClient,
    q: str,
    limit: int,
) -> FoodLookup:
    remote: RemoteStatus = "disabled"
    products: list[OffProduct] = []
    if openfoodfacts.enabled:
        # Outside any DB session: a slow remote must not hold a connection.
        try:
            products = await openfoodfacts.search(q, limit)
            remote = "ok"
        except OpenFoodFactsUnavailableError:
            remote = "unavailable"
    cached = await _cache(sessionmaker, user_id, products)
    async with sessionmaker() as session:
        local = await NutritionRepository(session, user_id).search_foods(q, limit=limit)
    seen = {v.food.id for v in local}
    merged = [*local, *(v for v in cached if v.food.id not in seen)][:limit]
    return FoodLookup(items=[FoodOut.from_view(v) for v in merged], remote=remote)


async def _cache(
    sessionmaker: SessionmakerDep, user_id: int, products: list[OffProduct]
) -> list[FoodView]:
    if not products:
        return []
    async with sessionmaker.begin() as session:
        repo = NutritionRepository(session, user_id)
        return await repo.views(await repo.cache_products(products))
