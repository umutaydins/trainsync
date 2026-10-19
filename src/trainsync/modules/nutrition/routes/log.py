"""`/v1/nutrition/log`: the food log, one idempotent entry per client-generated id."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import HTTPException, Path, Query, Response, status

from trainsync.core.deps import ClockDep, SessionmakerDep
from trainsync.core.errors import UNAUTHORIZED, Responses, error
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.nutrition.repository import LogValues, NutritionRepository
from trainsync.modules.nutrition.routes.common import nutrition_router, today
from trainsync.modules.nutrition.schemas import DayLog, LogIn, LogOut

router = nutrition_router()

LOG_NOT_FOUND: Responses = {404: error("Unknown client id", "log entry not found")}
CLIENT_ID_EXAMPLE = "0b6f1f9e-4c1e-4a8e-9a43-2f1d8f0c6a11"


@router.get(
    "/log",
    summary="Food log of a day",
    description="Entries of one day (default: today, UTC), in meal order, then as logged.",
    response_model=DayLog,
    responses={**UNAUTHORIZED},
)
async def day_log(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    day: Annotated[date | None, Query(alias="date", examples=["2026-10-14"])] = None,
) -> DayLog:
    day = day or today(clock)
    async with sessionmaker() as session:
        rows = await NutritionRepository(session, principal.user_id).log_entries(day, day)
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
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    response: Response,
    client_id: Annotated[uuid.UUID, Path(examples=[CLIENT_ID_EXAMPLE])],
    body: LogIn,
) -> LogOut:
    async with sessionmaker.begin() as session:
        repo = NutritionRepository(session, principal.user_id)
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
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    client_id: Annotated[uuid.UUID, Path(examples=[CLIENT_ID_EXAMPLE])],
) -> Response:
    async with sessionmaker.begin() as session:
        deleted = await NutritionRepository(session, principal.user_id).delete_log(client_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "log entry not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
