"""`/v1/nutrition`: foods (local + Open Food Facts lookup), food log, profile, summaries.

Energy balance is an estimate (ADR 0019): BMR (Mifflin-St Jeor) x everyday baseline plus the
exercise energy of synced activities where Strava knows it. Unknown inputs stay unknown and are
flagged, never guessed. Days are UTC days, like the rest of the read API.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.core.clock import Clock
from trainsync.core.deps import ClockDep, SessionmakerDep, require_api_key
from trainsync.core.errors import UNAUTHORIZED, Responses, error
from trainsync.integrations.openfoodfacts.client import (
    OffProduct,
    OpenFoodFactsClient,
    OpenFoodFactsUnavailableError,
)
from trainsync.modules.activities.reads import week_start
from trainsync.modules.nutrition.energy import KcalSource, per_grams, target_warning, tenth
from trainsync.modules.nutrition.models import (
    ActivityBaseline,
    Food,
    FoodGroup,
    FoodLog,
    FoodSource,
    Meal,
    NutritionProfile,
    Sex,
)
from trainsync.modules.nutrition.repository import LogValues, NutritionRepository, ProfileValues
from trainsync.modules.nutrition.summary import DayEnergy, EstimateGap, energy_days, estimate_bmr
from trainsync.modules.nutrition.summary import latest_weight as latest_body_weight

router = APIRouter(
    prefix="/v1/nutrition", tags=["nutrition"], dependencies=[Depends(require_api_key)]
)

MAX_RANGE_DAYS = 92
BARCODE_PATTERN = r"^\d{8,14}$"
# `date` is also a field name below; this alias keeps it usable as a type there.
Day = date


def get_openfoodfacts(request: Request) -> OpenFoodFactsClient:
    client: OpenFoodFactsClient = request.app.state.openfoodfacts
    return client


OpenFoodFactsDep = Annotated[OpenFoodFactsClient, Depends(get_openfoodfacts)]


def _f(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


# ---------------------------------------------------------------- foods

FOOD_EXAMPLE: dict[str, Any] = {
    "id": 7,
    "name": "Rolled oats",
    "brand": "Acme",
    "barcode": "8690000000017",
    "kcal_100g": 372.0,
    "protein_100g": 13.5,
    "carbs_100g": 58.7,
    "fat_100g": 7.0,
    "sugars_100g": 1.1,
    "nova_group": 1,
    "food_group": "other",
    "source": "openfoodfacts",
    "favorite": True,
}
FOOD_IN_EXAMPLE: dict[str, Any] = {
    "name": "Chicken breast, cooked",
    "brand": None,
    "barcode": None,
    "kcal_100g": 165,
    "protein_100g": 31,
    "carbs_100g": 0,
    "fat_100g": 3.6,
    "favorite": False,
}

Kcal100 = Annotated[float, Field(ge=0, le=1000, description="kcal per 100 g")]
Macro100 = Annotated[float | None, Field(ge=0, le=100, description="g per 100 g; null = unknown")]
Nova = Annotated[
    int | None,
    Field(
        ge=1, le=4, description="Open Food Facts NOVA group, 4 = ultra-processed; null = unknown"
    ),
]


GroupField = Annotated[
    FoodGroup | None,
    Field(
        description="Decides whether the sugar is free sugar (sweets, dessert, sugary_drink"
        " count; fruit, vegetable, plain_dairy never do); null = unknown"
    ),
]


class FoodOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [FOOD_EXAMPLE]})

    id: int
    name: str
    brand: str | None
    barcode: str | None
    kcal_100g: float
    protein_100g: float | None = Field(description="null = unknown")
    carbs_100g: float | None = Field(description="null = unknown")
    fat_100g: float | None = Field(description="null = unknown")
    sugars_100g: float | None = Field(default=None, description="null = unknown")
    nova_group: Nova = None
    food_group: GroupField = None
    source: FoodSource = Field(description="`openfoodfacts` rows are cached lookups")
    favorite: bool

    @classmethod
    def from_row(cls, row: Food) -> "FoodOut":
        return cls(
            id=row.id,
            name=row.name,
            brand=row.brand,
            barcode=row.barcode,
            kcal_100g=float(row.kcal_100g),
            protein_100g=_f(row.protein_100g),
            carbs_100g=_f(row.carbs_100g),
            fat_100g=_f(row.fat_100g),
            sugars_100g=_f(row.sugars_100g),
            nova_group=row.nova_group,
            food_group=FoodGroup(row.food_group) if row.food_group else None,
            source=FoodSource(row.source),
            favorite=row.favorite,
        )


class FoodIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [FOOD_IN_EXAMPLE]})

    name: Annotated[str, Field(min_length=1, max_length=200)]
    brand: Annotated[str | None, Field(max_length=200)] = None
    barcode: Annotated[str | None, Field(pattern=BARCODE_PATTERN)] = None
    kcal_100g: Kcal100
    protein_100g: Macro100 = None
    carbs_100g: Macro100 = None
    fat_100g: Macro100 = None
    sugars_100g: Macro100 = None
    nova_group: Nova = None
    food_group: GroupField = None
    favorite: bool = False


class FoodPatch(BaseModel):
    """Only the fields sent are changed."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"kcal_100g": 380, "protein_100g": 13}]}
    )

    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    brand: Annotated[str | None, Field(max_length=200)] = None
    kcal_100g: Annotated[float | None, Field(ge=0, le=1000)] = None
    protein_100g: Macro100 = None
    carbs_100g: Macro100 = None
    fat_100g: Macro100 = None
    sugars_100g: Macro100 = None
    nova_group: Nova = None
    food_group: GroupField = None


class FoodList(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [FOOD_EXAMPLE]}]})

    items: list[FoodOut]


RemoteStatus = Literal["ok", "cached", "not_found", "unavailable", "disabled"]


class FoodLookup(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"items": [FOOD_EXAMPLE], "remote": "ok"}]}
    )

    items: list[FoodOut]
    remote: RemoteStatus = Field(
        description=(
            "Open Food Facts outcome: `ok` (asked, results cached), `cached` (barcode already "
            "stored, not asked), `not_found`, `unavailable` (timeout / error: local results "
            "only), `disabled` (`OPENFOODFACTS_ENABLED=false`: local results only)"
        )
    )


FOOD_NOT_FOUND: Responses = {404: error("Unknown food", "food not found")}


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
    sessionmaker: SessionmakerDep,
    q: Annotated[str | None, Query(max_length=100, examples=["oats"])] = None,
    favorites: Annotated[bool, Query(description="Only favorites")] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> FoodList:
    async with sessionmaker() as session:
        rows = await NutritionRepository(session).search_foods(
            q, favorites_only=favorites, limit=limit
        )
    return FoodList(items=[FoodOut.from_row(r) for r in rows])


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
    sessionmaker: SessionmakerDep,
    openfoodfacts: OpenFoodFactsDep,
    barcode: Annotated[
        str | None, Query(pattern=BARCODE_PATTERN, examples=["8690000000017"])
    ] = None,
    q: Annotated[str | None, Query(min_length=2, max_length=100, examples=["oats"])] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> FoodLookup:
    if (barcode is None) == (q is None):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "pass barcode or q")
    if barcode is not None:
        return await _lookup_barcode(sessionmaker, openfoodfacts, barcode)
    return await _lookup_query(sessionmaker, openfoodfacts, q or "", limit)


async def _lookup_barcode(
    sessionmaker: SessionmakerDep, openfoodfacts: OpenFoodFactsClient, barcode: str
) -> FoodLookup:
    async with sessionmaker() as session:
        local = await NutritionRepository(session).food_by_barcode(barcode)
    if local is not None:
        return FoodLookup(items=[FoodOut.from_row(local)], remote="cached")
    if not openfoodfacts.enabled:
        return FoodLookup(items=[], remote="disabled")
    try:
        product = await openfoodfacts.product(barcode)
    except OpenFoodFactsUnavailableError:
        return FoodLookup(items=[], remote="unavailable")
    if product is None:
        return FoodLookup(items=[], remote="not_found")
    rows = await _cache(sessionmaker, [product])
    return FoodLookup(items=[FoodOut.from_row(r) for r in rows], remote="ok")


async def _lookup_query(
    sessionmaker: SessionmakerDep, openfoodfacts: OpenFoodFactsClient, q: str, limit: int
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
    cached = await _cache(sessionmaker, products)
    async with sessionmaker() as session:
        local = await NutritionRepository(session).search_foods(q, limit=limit)
    seen = {f.id for f in local}
    merged = [*local, *(f for f in cached if f.id not in seen)][:limit]
    return FoodLookup(items=[FoodOut.from_row(r) for r in merged], remote=remote)


async def _cache(sessionmaker: SessionmakerDep, products: list[OffProduct]) -> list[Food]:
    if not products:
        return []
    async with sessionmaker.begin() as session:
        return await NutritionRepository(session).cache_products(products)


@router.post(
    "/foods",
    summary="Create a food",
    description="A manual food with per-100 g values. Unknown macros may be null.",
    response_model=FoodOut,
    status_code=status.HTTP_201_CREATED,
    responses={**UNAUTHORIZED, 409: error("Barcode already stored", "barcode already exists")},
)
async def create_food(sessionmaker: SessionmakerDep, body: FoodIn) -> FoodOut:
    food = Food(
        name=body.name.strip(),
        brand=body.brand,
        barcode=body.barcode,
        kcal_100g=_dec(body.kcal_100g),
        protein_100g=_dec(body.protein_100g),
        carbs_100g=_dec(body.carbs_100g),
        fat_100g=_dec(body.fat_100g),
        sugars_100g=_dec(body.sugars_100g),
        nova_group=body.nova_group,
        food_group=body.food_group,
        source=FoodSource.MANUAL.value,
        favorite=body.favorite,
    )
    try:
        async with sessionmaker.begin() as session:
            await NutritionRepository(session).add_food(food)
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "barcode already exists") from exc
    return FoodOut.from_row(food)


@router.patch(
    "/foods/{food_id}",
    summary="Update a food",
    description=(
        "Changes only the fields sent. Editing a cached Open Food Facts food turns it into a "
        "`manual` one, so a later lookup never overwrites the edit. Logged entries use the "
        "food's current values."
    ),
    response_model=FoodOut,
    responses={
        **UNAUTHORIZED,
        **FOOD_NOT_FOUND,
        400: error("A required field set to null", "name cannot be null"),
    },
)
async def update_food(
    sessionmaker: SessionmakerDep,
    food_id: Annotated[int, Path(examples=[7])],
    body: FoodPatch,
) -> FoodOut:
    changes = body.model_dump(exclude_unset=True)
    for required in ("name", "kcal_100g"):
        if required in changes and changes[required] is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{required} cannot be null")
    async with sessionmaker.begin() as session:
        food = await NutritionRepository(session).food(food_id)
        if food is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "food not found")
        for field, value in changes.items():
            setattr(food, field, _patch_value(field, value))
        if changes:
            food.source = FoodSource.MANUAL.value
            await session.flush()
            await session.refresh(food)
    return FoodOut.from_row(food)


@router.put(
    "/foods/{food_id}/favorite",
    summary="Mark a food as favorite",
    description="Idempotent.",
    response_model=FoodOut,
    responses={**UNAUTHORIZED, **FOOD_NOT_FOUND},
)
async def favorite_food(
    sessionmaker: SessionmakerDep, food_id: Annotated[int, Path(examples=[7])]
) -> FoodOut:
    return await _set_favorite(sessionmaker, food_id, favorite=True)


@router.delete(
    "/foods/{food_id}/favorite",
    summary="Unmark a favorite food",
    description="Idempotent.",
    response_model=FoodOut,
    responses={**UNAUTHORIZED, **FOOD_NOT_FOUND},
)
async def unfavorite_food(
    sessionmaker: SessionmakerDep, food_id: Annotated[int, Path(examples=[7])]
) -> FoodOut:
    return await _set_favorite(sessionmaker, food_id, favorite=False)


async def _set_favorite(sessionmaker: SessionmakerDep, food_id: int, *, favorite: bool) -> FoodOut:
    async with sessionmaker.begin() as session:
        food = await NutritionRepository(session).set_favorite(food_id, favorite)
    if food is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "food not found")
    return FoodOut.from_row(food)


def _dec(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _patch_value(field: str, value: object) -> object:
    if isinstance(value, str) and field == "name":
        return value.strip()
    if field in ("nova_group", "food_group"):
        return value
    return Decimal(str(value)) if isinstance(value, float | int) else value


# ---------------------------------------------------------------- food log

LOG_IN_EXAMPLE: dict[str, Any] = {
    "date": "2026-10-14",
    "meal": "breakfast",
    "food_id": 7,
    "grams": 80,
}
LOG_EXAMPLE: dict[str, Any] = {
    "client_id": "0b6f1f9e-4c1e-4a8e-9a43-2f1d8f0c6a11",
    **LOG_IN_EXAMPLE,
    "food_name": "Rolled oats",
    "brand": "Acme",
    "kcal": 297.6,
    "protein_g": 10.8,
    "carbs_g": 47.0,
    "fat_g": 5.6,
    "sugars_g": 0.9,
    "sugars_100g": 1.1,
    "nova_group": 1,
    "food_group": "other",
    "created_at": "2026-10-14T07:12:03Z",
}


class LogIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [LOG_IN_EXAMPLE]})

    date: date
    meal: Meal
    food_id: int
    grams: Annotated[float, Field(gt=0, le=5000)]


class LogOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [LOG_EXAMPLE]})

    client_id: uuid.UUID
    date: date
    meal: Meal
    food_id: int
    food_name: str
    brand: str | None
    grams: float
    kcal: float
    protein_g: float | None = Field(description="null when the food's value is unknown")
    carbs_g: float | None = Field(description="null when the food's value is unknown")
    fat_g: float | None = Field(description="null when the food's value is unknown")
    sugars_g: float | None = Field(
        default=None, description="null when the food's value is unknown"
    )
    sugars_100g: float | None = Field(default=None, description="Snapshot; null = unknown")
    nova_group: Nova = None
    food_group: GroupField = None
    created_at: datetime

    @classmethod
    def from_rows(cls, log: FoodLog, food: Food) -> "LogOut":
        def amount(per_100g: Decimal | None) -> float | None:
            return None if per_100g is None else float(tenth(per_grams(per_100g, log.grams)))

        return cls(
            client_id=log.client_id,
            date=log.date,
            meal=Meal(log.meal),
            food_id=food.id,
            food_name=food.name,
            brand=food.brand,
            grams=float(log.grams),
            # Snapshotted at log time: editing the food later does not change this entry.
            kcal=float(tenth(per_grams(log.kcal_100g, log.grams))),
            protein_g=amount(log.protein_100g),
            carbs_g=amount(log.carbs_100g),
            fat_g=amount(log.fat_100g),
            sugars_g=amount(log.sugars_100g),
            sugars_100g=_f(log.sugars_100g),
            nova_group=log.nova_group,
            food_group=FoodGroup(log.food_group) if log.food_group else None,
            created_at=log.created_at,
        )


class DayLog(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"date": "2026-10-14", "entries": [LOG_EXAMPLE]}]}
    )

    date: date
    entries: list[LogOut] = Field(description="In meal order, then as logged")


LOG_NOT_FOUND: Responses = {404: error("Unknown client id", "log entry not found")}


@router.get(
    "/log",
    summary="Food log of a day",
    description="Entries of one day (default: today, UTC), in meal order, then as logged.",
    response_model=DayLog,
    responses={**UNAUTHORIZED},
)
async def day_log(
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    day: Annotated[date | None, Query(alias="date", examples=["2026-10-14"])] = None,
) -> DayLog:
    day = day or _today(clock)
    async with sessionmaker() as session:
        rows = await NutritionRepository(session).log_entries(day, day)
    return DayLog(date=day, entries=[LogOut.from_rows(log, food) for log, food in rows])


@router.put(
    "/log/{client_id}",
    summary="Log food (idempotent)",
    description=(
        "Upsert by the client-generated `client_id`: `201` when it created the entry, `200` "
        "when an entry with this id already existed and was updated. Retrying the same request "
        "stores one entry. The food's kcal and macros are copied into the entry, so editing the "
        "food later does not change past days."
    ),
    response_model=LogOut,
    status_code=status.HTTP_200_OK,
    responses={
        **UNAUTHORIZED,
        201: {"description": "Created", "model": LogOut},
        404: error("Unknown food", "food not found"),
    },
)
async def put_log(
    sessionmaker: SessionmakerDep,
    response: Response,
    client_id: Annotated[uuid.UUID, Path(examples=["0b6f1f9e-4c1e-4a8e-9a43-2f1d8f0c6a11"])],
    body: LogIn,
) -> LogOut:
    async with sessionmaker.begin() as session:
        repo = NutritionRepository(session)
        food = await repo.food(body.food_id)
        if food is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "food not found")
        values = LogValues(body.date, body.meal.value, food, Decimal(str(body.grams)))
        log, created = await repo.put_log(client_id, values)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return LogOut.from_rows(log, food)


@router.delete(
    "/log/{client_id}",
    summary="Delete a food log entry",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**UNAUTHORIZED, **LOG_NOT_FOUND},
)
async def delete_log(
    sessionmaker: SessionmakerDep,
    client_id: Annotated[uuid.UUID, Path(examples=["0b6f1f9e-4c1e-4a8e-9a43-2f1d8f0c6a11"])],
) -> Response:
    async with sessionmaker.begin() as session:
        deleted = await NutritionRepository(session).delete_log(client_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "log entry not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- profile

PROFILE_IN_EXAMPLE: dict[str, Any] = {
    "sex": "male",
    "birth_year": 1991,
    "height_cm": 180,
    "activity_baseline": "light",
    "kcal_target": 2600,
    "protein_target_g": 140,
}
PROFILE_EXAMPLE: dict[str, Any] = {
    **PROFILE_IN_EXAMPLE,
    "bmr_kcal": 1795.0,
    "weight_kg": 80.0,
    "weight_date": "2026-10-12",
    "estimate_unavailable_reason": None,
    "warning": None,
    "updated_at": "2026-10-12T19:00:00Z",
}


class ProfileIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [PROFILE_IN_EXAMPLE]})

    sex: Sex = Field(description="Only used by the BMR equation")
    birth_year: Annotated[int, Field(ge=1900, le=2100)]
    height_cm: Annotated[float, Field(ge=100, le=250)]
    activity_baseline: ActivityBaseline = Field(
        description="Everyday activity outside logged exercise: BMR x 1.2 / 1.375 / 1.55"
    )
    kcal_target: Annotated[int | None, Field(ge=1, le=10000)] = None
    protein_target_g: Annotated[int | None, Field(ge=0, le=1000)] = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [PROFILE_EXAMPLE]})

    sex: Sex
    birth_year: int
    height_cm: float
    activity_baseline: ActivityBaseline
    kcal_target: int | None
    protein_target_g: int | None
    bmr_kcal: float | None = Field(
        description="Estimated BMR today (Mifflin-St Jeor, latest body weight); null if unknown"
    )
    weight_kg: float | None = Field(description="The body weight the estimate used")
    weight_date: date | None
    estimate_unavailable_reason: EstimateGap | None = Field(
        description="Why `bmr_kcal` is null (`no_body_weight`)"
    )
    warning: str | None = Field(
        description="Set when `kcal_target` is below the estimated BMR; the target is kept"
    )
    updated_at: datetime


@router.get(
    "/profile",
    summary="Nutrition profile",
    description="Profile, targets and today's BMR estimate.",
    response_model=ProfileOut,
    responses={**UNAUTHORIZED, 404: error("No profile yet", "profile not set")},
)
async def get_profile(sessionmaker: SessionmakerDep, clock: ClockDep) -> ProfileOut:
    async with sessionmaker() as session:
        profile = await NutritionRepository(session).profile()
        if profile is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not set")
        return await _profile_out(session, profile, _today(clock))


@router.put(
    "/profile",
    summary="Set the nutrition profile",
    description=(
        "Replaces the profile. A `kcal_target` below the estimated BMR is accepted and comes "
        "back with a `warning`."
    ),
    response_model=ProfileOut,
    responses={**UNAUTHORIZED},
)
async def put_profile(
    sessionmaker: SessionmakerDep, clock: ClockDep, body: ProfileIn
) -> ProfileOut:
    values = ProfileValues(
        sex=body.sex.value,
        birth_year=body.birth_year,
        height_cm=Decimal(str(body.height_cm)),
        activity_baseline=body.activity_baseline.value,
        kcal_target=body.kcal_target,
        protein_target_g=body.protein_target_g,
    )
    async with sessionmaker.begin() as session:
        profile = await NutritionRepository(session).put_profile(values, clock())
        return await _profile_out(session, profile, _today(clock))


async def _profile_out(session: AsyncSession, profile: NutritionProfile, today: date) -> ProfileOut:
    weight = await latest_body_weight(session, today)
    bmr = estimate_bmr(profile, weight, today)
    return ProfileOut(
        sex=Sex(profile.sex),
        birth_year=profile.birth_year,
        height_cm=float(profile.height_cm),
        activity_baseline=ActivityBaseline(profile.activity_baseline),
        kcal_target=profile.kcal_target,
        protein_target_g=profile.protein_target_g,
        bmr_kcal=_f(bmr.bmr),
        weight_kg=_f(weight.weight_kg) if weight else None,
        weight_date=weight.date if weight else None,
        estimate_unavailable_reason=bmr.gap,
        warning=target_warning(profile.kcal_target, bmr.bmr),
        updated_at=profile.updated_at,
    )


# ---------------------------------------------------------------- summaries

ACTIVITY_ENERGY_EXAMPLE: dict[str, Any] = {
    "strava_activity_id": 10000000123,
    "name": "Evening Ride",
    "sport_type": "Ride",
    "start_date": "2026-10-14T16:00:00Z",
    "kcal": 650.0,
    "kcal_known": True,
    "kcal_source": "kilojoules",
}
DAY_EXAMPLE: dict[str, Any] = {
    "date": "2026-10-14",
    "intake_kcal": 2410.5,
    "protein_g": 131.2,
    "carbs_g": 270.0,
    "fat_g": 80.4,
    "sugars_g": 41.5,
    "free_sugars_g": 18.0,
    "entry_count": 9,
    "macros_complete": True,
    "kcal_target": 2600,
    "protein_target_g": 140,
    "kcal_remaining": 189.5,
    "bmr_kcal": 1795.0,
    "baseline_kcal": 2468.1,
    "activity_baseline": "light",
    "weight_kg": 80.0,
    "weight_date": "2026-10-12",
    "estimate_unavailable_reason": None,
    "exercise_kcal": 650.0,
    "exercise_unknown_count": 0,
    "exercise_complete": True,
    "activities": [ACTIVITY_ENERGY_EXAMPLE],
    "expenditure_kcal": 3118.1,
    "balance_kcal": -707.6,
    "balance_complete": True,
}


class ActivityEnergyOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [ACTIVITY_ENERGY_EXAMPLE]})

    strava_activity_id: int
    name: str
    sport_type: str
    start_date: datetime
    kcal: float | None = Field(description="null = unknown (not guessed)")
    kcal_known: bool
    kcal_source: KcalSource | None = Field(
        description="`calories` (Strava's estimate) or `kilojoules` (rides: kJ ≈ kcal)"
    )


class DaySummary(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [DAY_EXAMPLE]})

    date: date
    intake_kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    sugars_g: float = Field(default=0.0, description="Known sugar values only")
    free_sugars_g: float = Field(
        default=0.0,
        description="The part of sugars_g that counts toward the daily sugar limit:"
        " sweets, desserts, sugary drinks and NOVA 4 foods; never fruit, vegetables, plain dairy",
    )
    entry_count: int
    macros_complete: bool = Field(
        description="False if a logged food has an unknown macro (missing from the sums)"
    )
    kcal_target: int | None
    protein_target_g: int | None
    kcal_remaining: float | None = Field(description="kcal_target - intake_kcal")
    bmr_kcal: float | None = Field(description="Mifflin-St Jeor estimate; null if unknown")
    baseline_kcal: float | None = Field(
        description="BMR x activity_baseline multiplier, logged exercise excluded"
    )
    activity_baseline: ActivityBaseline | None
    weight_kg: float | None = Field(description="Latest body weight on or before the day")
    weight_date: Day | None
    estimate_unavailable_reason: EstimateGap | None = Field(
        description="Why BMR/baseline/expenditure/balance are null"
    )
    exercise_kcal: float = Field(description="Sum over activities whose energy is known")
    exercise_unknown_count: int = Field(description="Activities whose energy is unknown")
    exercise_complete: bool = Field(description="Every activity of the day has a known energy")
    activities: list[ActivityEnergyOut] = Field(description="Synced activities, UTC day")
    expenditure_kcal: float | None = Field(description="baseline_kcal + exercise_kcal")
    balance_kcal: float | None = Field(
        description="intake_kcal - expenditure_kcal; negative = deficit"
    )
    balance_complete: bool = Field(
        description="False when the balance leaves out unknown exercise or cannot be computed"
    )

    @classmethod
    def from_energy(cls, d: DayEnergy) -> "DaySummary":
        profile = d.profile
        target = profile.kcal_target if profile else None
        weight = d.bmr.weight
        return cls(
            date=d.day,
            intake_kcal=float(d.intake.kcal),
            protein_g=float(d.intake.protein_g),
            carbs_g=float(d.intake.carbs_g),
            fat_g=float(d.intake.fat_g),
            sugars_g=float(d.intake.sugars_g),
            free_sugars_g=float(d.intake.free_sugars_g),
            entry_count=d.intake.entries,
            macros_complete=d.intake.macros_complete,
            kcal_target=target,
            protein_target_g=profile.protein_target_g if profile else None,
            kcal_remaining=None if target is None else float(target - d.intake.kcal),
            bmr_kcal=_f(d.bmr.bmr),
            baseline_kcal=_f(d.baseline_kcal),
            activity_baseline=ActivityBaseline(profile.activity_baseline) if profile else None,
            weight_kg=_f(weight.weight_kg) if weight else None,
            weight_date=weight.date if weight else None,
            estimate_unavailable_reason=d.bmr.gap,
            exercise_kcal=float(d.balance.exercise_kcal),
            exercise_unknown_count=d.balance.exercise_unknown,
            exercise_complete=d.balance.exercise_unknown == 0,
            activities=[
                ActivityEnergyOut(
                    strava_activity_id=a.strava_activity_id,
                    name=a.name,
                    sport_type=a.sport_type,
                    start_date=a.start_date,
                    kcal=_f(e.kcal),
                    kcal_known=e.known,
                    kcal_source=e.source,
                )
                for a, e in d.activities
            ],
            expenditure_kcal=_f(d.balance.expenditure_kcal),
            balance_kcal=_f(d.balance.balance_kcal),
            balance_complete=d.balance.complete,
        )


class RangeTotals(BaseModel):
    intake_kcal: float
    exercise_kcal: float = Field(description="Known exercise energy only")
    days_logged: int = Field(description="Days with at least one food log entry")
    avg_intake_kcal: float | None = Field(description="Over days_logged; null if none")
    balance_kcal: float | None = Field(
        description="Sum over the days that have a balance; null if none has"
    )
    balance_days: int = Field(description="Days included in balance_kcal")
    balance_complete: bool = Field(description="Every day has a complete balance")


class RangeSummary(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "from": "2026-10-12",
                    "to": "2026-10-18",
                    "days": [DAY_EXAMPLE],
                    "totals": {
                        "intake_kcal": 16210.4,
                        "exercise_kcal": 1850.0,
                        "days_logged": 7,
                        "avg_intake_kcal": 2315.8,
                        "balance_kcal": -2105.3,
                        "balance_days": 7,
                        "balance_complete": False,
                    },
                }
            ]
        },
        populate_by_name=True,
    )

    start: date = Field(alias="from")
    end: date = Field(alias="to")
    days: list[DaySummary]
    totals: RangeTotals


ESTIMATE_NOTE = (
    "All energy figures are estimates: BMR by Mifflin-St Jeor from the profile and the latest body "
    "weight on or before the day, times the everyday-activity multiplier (1.2 / 1.375 / 1.55) "
    "without exercise; exercise from synced activities (`raw.calories`, else for rides "
    "`raw.kilojoules` ≈ kcal, else unknown). Balance = intake - (baseline + known exercise). "
    "Unknown inputs are flagged, never guessed. Days are UTC days."
)


@router.get(
    "/summary",
    summary="Daily nutrition summary and energy balance",
    description=f"One day (default: today, UTC). {ESTIMATE_NOTE}",
    response_model=DaySummary,
    responses={**UNAUTHORIZED},
)
async def day_summary(
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    day: Annotated[date | None, Query(alias="date", examples=["2026-10-14"])] = None,
) -> DaySummary:
    day = day or _today(clock)
    async with sessionmaker() as session:
        (energy,) = await energy_days(session, day, day)
    return DaySummary.from_energy(energy)


@router.get(
    "/summary/weekly",
    summary="Nutrition summary per day for a range",
    description=(
        "One summary per day in `from`..`to` (both inclusive, at most 92 days) plus totals. "
        f"Defaults to the current ISO week (Monday to Sunday, UTC). {ESTIMATE_NOTE}"
    ),
    response_model=RangeSummary,
    response_model_by_alias=True,
    responses={
        **UNAUTHORIZED,
        400: error("`to` before `from`, or over 92 days", "`to` is before `from`"),
    },
)
async def range_summary(
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    start: Annotated[date | None, Query(alias="from", examples=["2026-10-12"])] = None,
    end: Annotated[date | None, Query(alias="to", examples=["2026-10-18"])] = None,
) -> RangeSummary:
    start, end = _resolve_range(start, end, clock)
    async with sessionmaker() as session:
        energy = await energy_days(session, start, end)
    days = [DaySummary.from_energy(d) for d in energy]
    return RangeSummary.model_validate(
        {"from": start, "to": end, "days": days, "totals": _totals(energy)}
    )


def _totals(energy: list[DayEnergy]) -> RangeTotals:
    logged = [d for d in energy if d.intake.entries]
    with_balance = [d.balance.balance_kcal for d in energy if d.balance.balance_kcal is not None]
    intake_kcal = sum((d.intake.kcal for d in energy), Decimal(0))
    return RangeTotals(
        intake_kcal=float(intake_kcal),
        exercise_kcal=float(sum((d.balance.exercise_kcal for d in energy), Decimal(0))),
        days_logged=len(logged),
        avg_intake_kcal=float(tenth(intake_kcal / len(logged))) if logged else None,
        balance_kcal=float(sum(with_balance, Decimal(0))) if with_balance else None,
        balance_days=len(with_balance),
        balance_complete=all(d.balance.complete for d in energy),
    )


def _today(clock: Clock) -> date:
    return clock().astimezone(UTC).date()


def _resolve_range(start: date | None, end: date | None, clock: Clock) -> tuple[date, date]:
    if end is not None:
        start = start or end - timedelta(days=6)
    else:
        start = start or week_start(_today(clock))
        end = start + timedelta(days=6)
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "`to` is before `from`")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"at most {MAX_RANGE_DAYS} days")
    return start, end
