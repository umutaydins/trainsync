"""`/v1/nutrition/foods`: search, create and edit stored foods."""

from decimal import Decimal
from typing import Annotated

from fastapi import HTTPException, Path, Query, status
from sqlalchemy.exc import IntegrityError

from trainsync.core.deps import SessionmakerDep
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.nutrition.models import Food, FoodSource
from trainsync.modules.nutrition.repository import NutritionRepository
from trainsync.modules.nutrition.routes.common import FOOD_NOT_FOUND, nutrition_router, to_decimal
from trainsync.modules.nutrition.schemas import FoodIn, FoodList, FoodOut, FoodPatch

router = nutrition_router()

MAX_QUERY_LENGTH = 100
DEFAULT_SEARCH_LIMIT, MAX_SEARCH_LIMIT = 50, 200
REQUIRED_FIELDS = ("name", "kcal_100g")
# Not converted to Decimal on patch: an int (NOVA) and an enum (food group).
PLAIN_FIELDS = ("nova_group", "food_group")


@router.get(
    "/foods",
    summary="Search stored foods",
    description=(
        "Local foods only (manual entries and cached Open Food Facts products): case-insensitive "
        "substring of name or brand, or an exact barcode. Favorites first, then by name."
    ),
    response_model=FoodList,
    responses={**UNAUTHORIZED},
)
async def search_foods(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    q: Annotated[str | None, Query(max_length=MAX_QUERY_LENGTH, examples=["oats"])] = None,
    favorites: Annotated[bool, Query(description="Only favorites")] = False,
    limit: Annotated[int, Query(ge=1, le=MAX_SEARCH_LIMIT)] = DEFAULT_SEARCH_LIMIT,
) -> FoodList:
    async with sessionmaker() as session:
        rows = await NutritionRepository(session, principal.user_id).search_foods(
            q, favorites_only=favorites, limit=limit
        )
    return FoodList(items=[FoodOut.from_view(r) for r in rows])


@router.post(
    "/foods",
    summary="Create a food",
    description="A manual food with per-100 g values. Unknown macros may be null.",
    response_model=FoodOut,
    status_code=status.HTTP_201_CREATED,
    responses={**UNAUTHORIZED, 409: error("Barcode already stored", "barcode already exists")},
)
async def create_food(
    principal: CurrentUser, sessionmaker: SessionmakerDep, body: FoodIn
) -> FoodOut:
    food = Food(
        name=body.name.strip(),
        brand=body.brand,
        barcode=body.barcode,
        kcal_100g=to_decimal(body.kcal_100g),
        protein_100g=to_decimal(body.protein_100g),
        carbs_100g=to_decimal(body.carbs_100g),
        fat_100g=to_decimal(body.fat_100g),
        sugars_100g=to_decimal(body.sugars_100g),
        nova_group=body.nova_group,
        food_group=body.food_group,
        source=FoodSource.MANUAL.value,
    )
    try:
        async with sessionmaker.begin() as session:
            view = await NutritionRepository(session, principal.user_id).add_food(
                food, favorite=body.favorite
            )
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "barcode already exists") from exc
    return FoodOut.from_view(view)


@router.patch(
    "/foods/{food_id}",
    summary="Update a food",
    description=(
        "Changes only the fields sent. Your own foods are yours to edit; shared ones (the Open "
        "Food Facts cache) only the owner may correct. Editing a cached Open Food Facts food "
        "turns it into a `manual` one, so a later lookup never overwrites the edit. Logged "
        "entries keep the values they were logged with."
    ),
    response_model=FoodOut,
    responses={
        **UNAUTHORIZED,
        **FOOD_NOT_FOUND,
        400: error("A required field set to null", "name cannot be null"),
        403: error("A shared food, and you are not the owner", "shared foods are owner-curated"),
    },
)
async def update_food(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    food_id: Annotated[int, Path(examples=[7])],
    body: FoodPatch,
) -> FoodOut:
    changes = body.model_dump(exclude_unset=True)
    for required in REQUIRED_FIELDS:
        if required in changes and changes[required] is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{required} cannot be null")
    async with sessionmaker.begin() as session:
        repo = NutritionRepository(session, principal.user_id)
        food = await repo.food(food_id)
        if food is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "food not found")
        if food.user_id is None and not principal.is_owner:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "shared foods are owner-curated")
        for field, value in changes.items():
            setattr(food, field, _patch_value(field, value))
        if changes:
            food.source = FoodSource.MANUAL.value
            await session.flush()
            await session.refresh(food)
        [view] = await repo.views([food])
    return FoodOut.from_view(view)


def _patch_value(field: str, value: object) -> object:
    if isinstance(value, str) and field == "name":
        return value.strip()
    if field in PLAIN_FIELDS:
        return value
    return Decimal(str(value)) if isinstance(value, float | int) else value
