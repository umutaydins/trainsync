"""`/v1/checkins`: the daily check-in (P6.9, ADR 0020).

Dates are the owner's local days (`CHECKIN_TZ`): the bot asks in the evening and stores the
answer under that day. `PUT /v1/checkins/{date}` is an idempotent upsert by date, so a retried or
repeated answer never creates a second row; a body weight is also written to `body_metrics`.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from trainsync.core.deps import ClockDep, SessionmakerDep, SettingsDep
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.core.localtime import local_today
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.checkin.models import CheckinStatus, DailyCheckin
from trainsync.modules.checkin.repository import CheckinRepository, CheckinValues
from trainsync.modules.checkin.streaks import adherence, current_streak, longest_streak
from trainsync.modules.training.repository import (
    BodyMetricRepository,
    ProgramRepository,
    WorkoutRepository,
)
from trainsync.modules.training.schemas import Kg

router = APIRouter(prefix="/v1/checkins", tags=["training"])

MAX_RANGE_DAYS = 400
BAD_RANGE = error("`to` before `from`, or too long", "`to` is before `from`")
NOT_FOUND = error("No check-in that day", "no check-in for this date")

CHECKIN_IN_EXAMPLE: dict[str, Any] = {
    "status": "done",
    "workout_id": 42,
    "reason_note": None,
    "sleep_hours": 7.5,
    "energy_1_5": 4,
    "body_weight_kg": 78.4,
}
CHECKIN_EXAMPLE: dict[str, Any] = {
    "date": "2026-10-18",
    **CHECKIN_IN_EXAMPLE,
    "created_at": "2026-10-18T18:05:00Z",
    "updated_at": "2026-10-18T18:07:30Z",
}
SKIPPED_EXAMPLE: dict[str, Any] = {"status": "skipped", "reason_note": "late meeting"}


class CheckinIn(BaseModel):
    """Replaces the day's check-in (every field; omitted ones become null)."""

    model_config = ConfigDict(json_schema_extra={"examples": [CHECKIN_IN_EXAMPLE, SKIPPED_EXAMPLE]})

    status: CheckinStatus
    workout_id: int | None = Field(default=None, description="The workout logged that day")
    reason_note: str | None = Field(default=None, max_length=500)
    sleep_hours: Decimal | None = Field(default=None, ge=0, le=24, decimal_places=1)
    energy_1_5: int | None = Field(default=None, ge=1, le=5)
    body_weight_kg: Decimal | None = Field(
        default=None, gt=0, lt=500, decimal_places=2, description="Also stored in body metrics"
    )


class CheckinOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [CHECKIN_EXAMPLE]})

    date: date
    status: CheckinStatus
    workout_id: int | None
    reason_note: str | None
    sleep_hours: Kg | None
    energy_1_5: int | None
    body_weight_kg: Kg | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: DailyCheckin) -> "CheckinOut":
        return cls(
            date=row.date,
            status=CheckinStatus(row.status),
            workout_id=row.workout_id,
            reason_note=row.reason_note,
            sleep_hours=row.sleep_hours,
            energy_1_5=row.energy_1_5,
            body_weight_kg=row.body_weight_kg,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class CheckinList(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"from": "2026-10-01", "to": "2026-10-18", "items": [CHECKIN_EXAMPLE]}]
        },
        populate_by_name=True,
    )

    start: date = Field(alias="from")
    end: date = Field(alias="to")
    items: list[CheckinOut] = Field(description="Oldest first; days without a check-in are absent")


class WeekOut(BaseModel):
    week_start: date = Field(description="Monday of the ISO week")
    planned: int
    done: int


SUMMARY_EXAMPLE: dict[str, Any] = {
    "from": "2026-09-28",
    "to": "2026-10-18",
    "today": "2026-10-18",
    "current_streak": 6,
    "longest_streak": 11,
    "days_per_week": 3,
    "planned_days": 9,
    "planned_days_done": 7,
    "adherence": 0.778,
    "counts": {"done": 6, "partial": 1, "skipped": 2, "rest": 8, "sick_or_injured": 0},
    "weeks": [{"week_start": "2026-09-28", "planned": 3, "done": 3}],
}


class CheckinSummary(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [SUMMARY_EXAMPLE]}, populate_by_name=True
    )

    start: date = Field(alias="from")
    end: date = Field(alias="to")
    today: date = Field(description="The local day (`CHECKIN_TZ`) the streak is counted to")
    current_streak: int = Field(
        description="Days in a row with a check-in that is not `skipped`, up to today (or "
        "yesterday while today has none yet)"
    )
    longest_streak: int
    days_per_week: int | None = Field(description="Of the active program; null without one")
    planned_days: int = Field(
        description="Per ISO week: min(days_per_week, days in range - sick/injured days)"
    )
    planned_days_done: int = Field(description="done + partial days, at most planned per week")
    adherence: float | None = Field(description="planned_days_done / planned_days; null if 0")
    counts: dict[CheckinStatus, int] = Field(description="Check-ins per status in the range")
    weeks: list[WeekOut]


def _range(
    start: date | None, end: date | None, today: date, default_days: int
) -> tuple[date, date]:
    end = end or today
    start = start or end - timedelta(days=default_days - 1)
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "`to` is before `from`")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"at most {MAX_RANGE_DAYS} days")
    return start, end


@router.get(
    "",
    summary="List check-ins",
    description="Check-ins in `from`..`to` (inclusive, local days); default: the last 12 weeks.",
    response_model=CheckinList,
    response_model_by_alias=True,
    responses={**UNAUTHORIZED, 400: BAD_RANGE},
)
async def list_checkins(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    settings: SettingsDep,
    clock: ClockDep,
    start: Annotated[date | None, Query(alias="from", examples=["2026-10-01"])] = None,
    end: Annotated[date | None, Query(alias="to", examples=["2026-10-18"])] = None,
) -> CheckinList:
    start, end = _range(start, end, local_today(clock, settings.checkin_zone), 84)
    async with sessionmaker() as session:
        rows = await CheckinRepository(session, principal.user_id).between(start, end)
    items = [CheckinOut.from_row(r) for r in rows]
    return CheckinList.model_validate({"from": start, "to": end, "items": items})


@router.get(
    "/summary",
    summary="Streak and adherence",
    description=(
        "Current and longest streak (consecutive days with a check-in that is not `skipped`) "
        "and adherence over `from`..`to` (default: the current ISO week and the three before "
        "it). Adherence = planned days done / planned days, where each ISO week plans "
        "`days_per_week` of the active program, capped by its days inside the range minus "
        "sick/injured days; done + partial days count as done (ADR 0020)."
    ),
    response_model=CheckinSummary,
    response_model_by_alias=True,
    responses={**UNAUTHORIZED, 400: BAD_RANGE},
)
async def checkin_summary(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    settings: SettingsDep,
    clock: ClockDep,
    start: Annotated[date | None, Query(alias="from", examples=["2026-09-28"])] = None,
    end: Annotated[date | None, Query(alias="to", examples=["2026-10-18"])] = None,
) -> CheckinSummary:
    today = local_today(clock, settings.checkin_zone)
    end = end or today
    start = start or end - timedelta(days=end.weekday() + 21)
    start, end = _range(start, end, today, 28)
    async with sessionmaker() as session:
        statuses = await CheckinRepository(session, principal.user_id).statuses(end)
        program = await ProgramRepository(session, principal.user_id).active()
    days_per_week = program.days_per_week if program is not None else None
    result = adherence(statuses, start, end, days_per_week)
    counts = {s: 0 for s in CheckinStatus}
    for day, value in statuses.items():
        if start <= day <= end:
            counts[value] += 1
    weeks = [WeekOut(week_start=w.week_start, planned=w.planned, done=w.done) for w in result.weeks]
    return CheckinSummary.model_validate(
        {
            "from": start,
            "to": end,
            "today": today,
            "current_streak": current_streak(statuses, min(today, end)),
            "longest_streak": longest_streak(statuses, end),
            "days_per_week": days_per_week,
            "planned_days": result.planned,
            "planned_days_done": result.done,
            "adherence": None if result.ratio is None else round(result.ratio, 3),
            "counts": counts,
            "weeks": weeks,
        }
    )


@router.get(
    "/{day}",
    summary="Get a day's check-in",
    response_model=CheckinOut,
    responses={**UNAUTHORIZED, 404: NOT_FOUND},
)
async def get_checkin(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    day: Annotated[date, Path(examples=["2026-10-18"])],
) -> CheckinOut:
    async with sessionmaker() as session:
        row = await CheckinRepository(session, principal.user_id).get(day)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no check-in for this date")
    return CheckinOut.from_row(row)


@router.put(
    "/{day}",
    summary="Save a day's check-in (idempotent)",
    description=(
        "Upsert by date: `201` when it created the check-in, `200` when it replaced it. The same "
        "request twice stores one row. `body_weight_kg` is also written to body metrics for "
        "that date; leaving it out later does not delete that body metric."
    ),
    response_model=CheckinOut,
    responses={
        **UNAUTHORIZED,
        201: {"description": "Created", "model": CheckinOut},
        400: error("Unknown workout", "workout not found"),
    },
)
async def put_checkin(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    response: Response,
    day: Annotated[date, Path(examples=["2026-10-18"])],
    body: CheckinIn,
) -> CheckinOut:
    async with sessionmaker.begin() as session:
        if (
            body.workout_id is not None
            and await WorkoutRepository(session, principal.user_id).get(body.workout_id) is None
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "workout not found")
        values = CheckinValues(
            status=body.status,
            workout_id=body.workout_id,
            reason_note=body.reason_note or None,
            sleep_hours=body.sleep_hours,
            energy_1_5=body.energy_1_5,
            body_weight_kg=body.body_weight_kg,
        )
        row, created = await CheckinRepository(session, principal.user_id).put(day, values, clock())
        if body.body_weight_kg is not None:
            await BodyMetricRepository(session, principal.user_id).put(day, body.body_weight_kg)
        out = CheckinOut.from_row(row)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return out
