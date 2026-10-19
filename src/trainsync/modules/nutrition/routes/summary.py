"""`/v1/nutrition/summary`: intake and estimated energy balance per day, and over a range.

Energy balance is an estimate (ADR 0019): BMR (Mifflin-St Jeor) x everyday baseline plus the
exercise energy of synced activities where Strava knows it. Unknown inputs stay unknown and are
flagged, never guessed. Days are UTC days, like the rest of the read API.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import HTTPException, Query, status

from trainsync.core.clock import Clock
from trainsync.core.deps import ClockDep, SessionmakerDep
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.modules.activities.reads import week_start
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.nutrition.energy import tenth
from trainsync.modules.nutrition.routes.common import nutrition_router, today
from trainsync.modules.nutrition.schemas import DaySummary, RangeSummary, RangeTotals
from trainsync.modules.nutrition.summary import DayEnergy, energy_days

router = nutrition_router()

MAX_RANGE_DAYS = 92
# A default range is one week: the start day plus six more.
WEEK_TAIL = timedelta(days=6)

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
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    day: Annotated[date | None, Query(alias="date", examples=["2026-10-14"])] = None,
) -> DaySummary:
    day = day or today(clock)
    async with sessionmaker() as session:
        (energy,) = await energy_days(session, principal.user_id, day, day)
    return DaySummary.from_energy(energy)


@router.get(
    "/summary/weekly",
    summary="Nutrition summary per day for a range",
    description=(
        f"One summary per day in `from`..`to` (both inclusive, at most {MAX_RANGE_DAYS} days) "
        "plus totals. Defaults to the current ISO week (Monday to Sunday, UTC). "
        f"{ESTIMATE_NOTE}"
    ),
    response_model=RangeSummary,
    response_model_by_alias=True,
    responses={
        **UNAUTHORIZED,
        400: error(f"`to` before `from`, or over {MAX_RANGE_DAYS} days", "`to` is before `from`"),
    },
)
async def range_summary(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    start: Annotated[date | None, Query(alias="from", examples=["2026-10-12"])] = None,
    end: Annotated[date | None, Query(alias="to", examples=["2026-10-18"])] = None,
) -> RangeSummary:
    start, end = _resolve_range(start, end, clock)
    async with sessionmaker() as session:
        energy = await energy_days(session, principal.user_id, start, end)
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


def _resolve_range(start: date | None, end: date | None, clock: Clock) -> tuple[date, date]:
    if end is not None:
        start = start or end - WEEK_TAIL
    else:
        start = start or week_start(today(clock))
        end = start + WEEK_TAIL
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "`to` is before `from`")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"at most {MAX_RANGE_DAYS} days")
    return start, end
