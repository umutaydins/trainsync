"""Summary schemas: one day's intake and energy balance, and a range of days with totals."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from trainsync.modules.nutrition.energy import KcalSource
from trainsync.modules.nutrition.models import ActivityBaseline
from trainsync.modules.nutrition.schemas.common import optional_float
from trainsync.modules.nutrition.summary import DayEnergy, EstimateGap

# `date` is also a field name below; this alias keeps it usable as a type there.
Day = date

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
RANGE_EXAMPLE: dict[str, Any] = {
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
            bmr_kcal=optional_float(d.bmr.bmr),
            baseline_kcal=optional_float(d.baseline_kcal),
            activity_baseline=ActivityBaseline(profile.activity_baseline) if profile else None,
            weight_kg=optional_float(weight.weight_kg) if weight else None,
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
                    kcal=optional_float(e.kcal),
                    kcal_known=e.known,
                    kcal_source=e.source,
                )
                for a, e in d.activities
            ],
            expenditure_kcal=optional_float(d.balance.expenditure_kcal),
            balance_kcal=optional_float(d.balance.balance_kcal),
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
        json_schema_extra={"examples": [RANGE_EXAMPLE]},
        populate_by_name=True,
    )

    start: date = Field(alias="from")
    end: date = Field(alias="to")
    days: list[DaySummary]
    totals: RangeTotals
