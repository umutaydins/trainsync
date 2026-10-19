"""`/v1/training/body-metrics`: body weight per day (upserted by date)."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from trainsync.core.deps import SessionmakerDep
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.training.repository import BodyMetricRepository
from trainsync.modules.training.schemas import Kg, check_range

router = APIRouter(prefix="/v1/training", tags=["training"])

BAD_RANGE = error("`to` before `from`", "`to` is before `from`")
MAX_WEIGHT_KG = 500  # exclusive


BODY_EXAMPLE: dict[str, Any] = {"date": "2026-10-18", "weight_kg": 78.4}


class BodyMetricIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"weight_kg": 78.4}]})

    weight_kg: Decimal = Field(gt=0, lt=MAX_WEIGHT_KG, decimal_places=2)


class BodyMetricOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [BODY_EXAMPLE]})

    date: date
    weight_kg: Kg


class BodyMetricList(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [BODY_EXAMPLE]}]})

    items: list[BodyMetricOut]


@router.put(
    "/body-metrics/{day}",
    summary="Record body weight for a day",
    description="Upsert by date (idempotent).",
    response_model=BodyMetricOut,
    responses={**UNAUTHORIZED},
)
async def put_body_metric(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    day: Annotated[date, Path(examples=["2026-10-18"])],
    body: BodyMetricIn,
) -> BodyMetricOut:
    async with sessionmaker.begin() as session:
        row = await BodyMetricRepository(session, principal.user_id).put(day, body.weight_kg)
        return BodyMetricOut(date=row.date, weight_kg=row.weight_kg)


@router.get(
    "/body-metrics",
    summary="List body metrics",
    description="Oldest first; `from`/`to` inclusive.",
    response_model=BodyMetricList,
    responses={**UNAUTHORIZED, 400: BAD_RANGE},
)
async def list_body_metrics(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    start: Annotated[date | None, Query(alias="from", examples=["2026-09-01"])] = None,
    end: Annotated[date | None, Query(alias="to", examples=["2026-10-31"])] = None,
) -> BodyMetricList:
    check_range(start, end)
    async with sessionmaker() as session:
        rows = await BodyMetricRepository(session, principal.user_id).between(start, end)
    return BodyMetricList(items=[BodyMetricOut(date=r.date, weight_kg=r.weight_kg) for r in rows])
