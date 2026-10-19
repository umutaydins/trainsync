"""Nutrition profile schemas: the inputs of the BMR estimate and the daily targets."""

from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from trainsync.modules.nutrition.models import ActivityBaseline, Sex
from trainsync.modules.nutrition.summary import EstimateGap

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

MIN_BIRTH_YEAR, MAX_BIRTH_YEAR = 1900, 2100
MIN_HEIGHT_CM, MAX_HEIGHT_CM = 100, 250
MAX_KCAL_TARGET = 10000
MAX_PROTEIN_TARGET_G = 1000


class ProfileIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [PROFILE_IN_EXAMPLE]})

    sex: Sex = Field(description="Only used by the BMR equation")
    birth_year: Annotated[int, Field(ge=MIN_BIRTH_YEAR, le=MAX_BIRTH_YEAR)]
    height_cm: Annotated[float, Field(ge=MIN_HEIGHT_CM, le=MAX_HEIGHT_CM)]
    activity_baseline: ActivityBaseline = Field(
        description="Everyday activity outside logged exercise: BMR x 1.2 / 1.375 / 1.55"
    )
    kcal_target: Annotated[int | None, Field(ge=1, le=MAX_KCAL_TARGET)] = None
    protein_target_g: Annotated[int | None, Field(ge=0, le=MAX_PROTEIN_TARGET_G)] = None


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
