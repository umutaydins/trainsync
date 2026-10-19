"""Response models of the progress statistics (P8.10, ADR 0038)."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from trainsync.modules.checkin.models import CheckinStatus
from trainsync.modules.stats.endurance import SportGroup
from trainsync.modules.stats.examples import HEATMAP_EXAMPLE, PRS_EXAMPLE, SERIES_EXAMPLE
from trainsync.modules.stats.periods import Bucket, Period, Window
from trainsync.modules.stats.series import Metric

PERCENT = 100
PCT_DIGITS = 1


class Change(BaseModel):
    """A number of the period, the same number of the previous period and the difference."""

    value: float | None
    previous: float | None = Field(description="null for `all` (no previous period)")
    change: float | None = Field(description="value - previous")
    change_pct: float | None = Field(description="change / previous x 100; null if previous is 0")


def change(value: float | None, previous: float | None, compared: bool = True) -> Change:
    if not compared:
        return Change(value=value, previous=None, change=None, change_pct=None)
    if value is None or previous is None:
        return Change(value=value, previous=previous, change=None, change_pct=None)
    diff = value - previous
    pct = round(diff / previous * PERCENT, PCT_DIGITS) if previous else None
    return Change(value=value, previous=previous, change=diff, change_pct=pct)


class WindowOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    start: date = Field(alias="from")
    end: date = Field(alias="to")
    days: int

    @classmethod
    def of(cls, window: Window) -> "WindowOut":
        return cls.model_validate({"from": window.start, "to": window.end, "days": window.days})


class EnduranceTotalsOut(BaseModel):
    count: Change
    distance_m: Change
    moving_time_s: Change
    elevation_gain_m: Change
    average_speed_mps: Change
    average_heartrate: Change = Field(description="Weighted by moving time; activities with HR")


class SportGroupOut(EnduranceTotalsOut):
    group: SportGroup


class EffortOut(BaseModel):
    group: SportGroup
    activity_id: int
    name: str
    start_date: datetime
    distance_m: float
    moving_time_s: int
    average_speed_mps: float | None


class EnduranceOut(BaseModel):
    totals: EnduranceTotalsOut
    by_group: list[SportGroupOut]
    longest: list[EffortOut] = Field(description="Greatest distance per sport group")
    fastest: list[EffortOut] = Field(
        description="Highest average speed per sport group (run/walk ≥ 1 km, ride ≥ 5 km, swim "
        "≥ 100 m)"
    )


class MuscleProgressOut(BaseModel):
    muscle: str
    sets: int
    tonnage_kg: float


class ExerciseProgressOut(BaseModel):
    exercise_id: int
    name: str
    muscle: str
    sets: int
    reps: int
    tonnage_kg: float
    best_e1rm_kg: Change = Field(description="Epley, working sets of at most 10 reps")


class AdherenceOut(BaseModel):
    program_id: int
    program_name: str
    planned_sessions: int
    done_sessions: int
    planned_sets: int
    done_sets: int
    session_ratio: float | None
    set_ratio: float | None


class StrengthOut(BaseModel):
    sessions: Change
    sets: Change = Field(description="Working sets (warm-ups excluded)")
    reps: Change
    tonnage_kg: Change = Field(description="Sum of weight x reps of the working sets")
    pr_count: Change = Field(description="Workouts that set a new e1RM record for a lift")
    by_muscle: list[MuscleProgressOut]
    by_exercise: list[ExerciseProgressOut]
    adherence: AdherenceOut | None = Field(description="Active program; null without one")


class ConsistencyOut(BaseModel):
    active_days: Change = Field(description="Local days with an activity or a workout")
    training_streak_weeks: int = Field(description="ISO weeks in a row with training, to today")
    longest_training_streak_weeks: int
    checkin_streak_days: int
    longest_checkin_streak_days: int
    checkin_rate: Change = Field(description="Days with a check-in / days of the period")
    sick_days: int = Field(description="Check-ins `sick_or_injured` in the period")


class NutritionOut(BaseModel):
    logged_days: Change
    logging_rate: Change = Field(description="Days with a food log / days of the period")
    avg_kcal: Change = Field(description="Mean over the logged days")
    kcal_target: int | None
    avg_protein_g: Change
    avg_carbs_g: Change
    avg_fat_g: Change
    days_over_sugar_limit: Change
    sugar_limit_g: float


class BodyOut(BaseModel):
    first_kg: float | None
    last_kg: float | None
    change_kg: Change
    moving_average_kg: float | None = Field(description="7-day moving average on the last day")
    rate_kg_per_week: Change = Field(description="Least-squares slope of the period's weights")
    body_fat_pct: float | None = Field(description="Phase 9; always null for now")


class ProgressOut(BaseModel):
    """The progress blocks of `/v1/stats/summary`."""

    model_config = ConfigDict(populate_by_name=True)

    period: Period
    timezone: str
    window: WindowOut
    previous: WindowOut | None
    endurance: EnduranceOut
    strength: StrengthOut
    consistency: ConsistencyOut
    nutrition: NutritionOut
    body: BodyOut


class PointOut(BaseModel):
    start: date = Field(description="First day of the bucket (may be before the window)")
    value: float | None
    moving_average: float | None = Field(
        default=None, description="weight_kg, bucket=day: the 7-day moving average"
    )


class SeriesOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [SERIES_EXAMPLE]})

    metric: Metric
    period: Period
    bucket: Bucket
    timezone: str
    window: WindowOut
    sport: SportGroup | None
    target: float | None = Field(description="kcal: the daily target; null for other metrics")
    points: list[PointOut]


class HeatmapDayOut(BaseModel):
    day: date
    value: float = Field(description="Training minutes (activities' moving time + workouts)")
    sessions: int
    checkin: CheckinStatus | None


class HeatmapOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [HEATMAP_EXAMPLE]})

    year: int = Field(description="The chosen year; for the last 12 months, the year of today")
    rolling: bool = Field(description="true: the last 12 months up to today (no `year` given)")
    window: WindowOut = Field(description="The days in `days`; never past today")
    timezone: str
    max_value: float
    days: list[HeatmapDayOut]


class PrOut(BaseModel):
    exercise_id: int
    name: str
    workout_id: int
    achieved_at: datetime
    e1rm_kg: float
    previous_kg: float | None = Field(description="The record it beat; null for the first")


class PrsOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [PRS_EXAMPLE]})

    period: Period
    window: WindowOut
    count: int
    records: list[PrOut] = Field(description="Newest first")
