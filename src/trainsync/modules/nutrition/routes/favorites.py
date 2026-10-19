"""`/v1/nutrition/foods/{food_id}/favorite`: mark and unmark favorite foods."""

from typing import Annotated

from fastapi import HTTPException, Path, status

from trainsync.core.deps import SessionmakerDep
from trainsync.core.errors import UNAUTHORIZED
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.nutrition.repository import NutritionRepository
from trainsync.modules.nutrition.routes.common import FOOD_NOT_FOUND, nutrition_router
from trainsync.modules.nutrition.schemas import FoodOut

router = nutrition_router()


@router.put(
    "/foods/{food_id}/favorite",
    summary="Mark a food as favorite",
    description="Idempotent.",
    response_model=FoodOut,
    responses={**UNAUTHORIZED, **FOOD_NOT_FOUND},
)
async def favorite_food(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    food_id: Annotated[int, Path(examples=[7])],
) -> FoodOut:
    return await _set_favorite(sessionmaker, principal.user_id, food_id, favorite=True)


@router.delete(
    "/foods/{food_id}/favorite",
    summary="Unmark a favorite food",
    description="Idempotent.",
    response_model=FoodOut,
    responses={**UNAUTHORIZED, **FOOD_NOT_FOUND},
)
async def unfavorite_food(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    food_id: Annotated[int, Path(examples=[7])],
) -> FoodOut:
    return await _set_favorite(sessionmaker, principal.user_id, food_id, favorite=False)


async def _set_favorite(
    sessionmaker: SessionmakerDep, user_id: int, food_id: int, *, favorite: bool
) -> FoodOut:
    async with sessionmaker.begin() as session:
        view = await NutritionRepository(session, user_id).set_favorite(food_id, favorite)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "food not found")
    return FoodOut.from_view(view)
