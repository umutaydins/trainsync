"""Energy balance: intake, BMR, everyday baseline, exercise from synced activities (ADR 0019).

Pure functions over plain values, so the API, the bot and the tests share one definition.
Everything here is an *estimate*. Inputs that are missing stay missing: an unknown activity
energy or a missing profile/body weight is reported as unknown, never guessed. kcal and grams
are `Decimal`, rounded to 0.1, half up, only at the end.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from trainsync.modules.nutrition.models import ActivityBaseline, Sex
from trainsync.modules.nutrition.sugar import counts_as_free_sugar

TENTH = Decimal("0.1")

# Everyday activity outside logged exercise, applied to BMR only (exercise is added separately,
# so it is never counted twice).
BASELINE_MULTIPLIER: Mapping[ActivityBaseline, Decimal] = {
    ActivityBaseline.SEDENTARY: Decimal("1.2"),
    ActivityBaseline.LIGHT: Decimal("1.375"),
    ActivityBaseline.MODERATE: Decimal("1.55"),
}


def tenth(value: Decimal) -> Decimal:
    return value.quantize(TENTH, rounding=ROUND_HALF_UP)


def age_on(birth_year: int, day: date) -> int:
    """Age in the calendar year of `day` (only the birth year is stored)."""
    return day.year - birth_year


def bmr_mifflin_st_jeor(sex: Sex, weight_kg: Decimal, height_cm: Decimal, age: int) -> Decimal:
    """Mifflin-St Jeor: `10w + 6.25h - 5a + 5` (male), `… - 161` (female)."""
    base = 10 * weight_kg + Decimal("6.25") * height_cm - 5 * age
    return tenth(base + (5 if sex is Sex.MALE else -161))


def baseline_kcal(bmr: Decimal, baseline: ActivityBaseline) -> Decimal:
    """BMR x everyday-activity multiplier, logged exercise excluded."""
    return tenth(bmr * BASELINE_MULTIPLIER[baseline])


def target_warning(kcal_target: int | None, bmr: Decimal | None) -> str | None:
    """A neutral note when the target is below the estimated BMR; the target is still kept."""
    if kcal_target is None or bmr is None or kcal_target >= bmr:
        return None
    return (
        f"kcal_target ({kcal_target} kcal) is below the estimated basal metabolic rate "
        f"({bmr} kcal). It was saved as entered; the BMR is an estimate."
    )


# ---------------------------------------------------------------- exercise


class KcalSource(StrEnum):
    CALORIES = "calories"  # Strava's own estimate on a detailed activity
    KILOJOULES = "kilojoules"  # rides: mechanical work in kJ ≈ kcal burned


@dataclass(frozen=True, slots=True)
class ActivityEnergy:
    kcal: Decimal | None
    source: KcalSource | None

    @property
    def known(self) -> bool:
        return self.kcal is not None


def _positive(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return Decimal(str(value)) if value > 0 else None


def activity_kcal(sport_type: str, raw: Mapping[str, object]) -> ActivityEnergy:
    """`raw.calories` when present and positive, else for rides `raw.kilojoules` (≈ kcal at
    ~24 % gross efficiency), else unknown. A zero `calories` means Strava had nothing to base
    it on, so it is treated as missing."""
    calories = _positive(raw.get("calories"))
    if calories is not None:
        return ActivityEnergy(tenth(calories), KcalSource.CALORIES)
    if "Ride" in sport_type:
        kilojoules = _positive(raw.get("kilojoules"))
        if kilojoules is not None:
            return ActivityEnergy(tenth(kilojoules), KcalSource.KILOJOULES)
    return ActivityEnergy(None, None)


# ---------------------------------------------------------------- intake


@dataclass(frozen=True, slots=True)
class IntakeEntry:
    grams: Decimal
    kcal_100g: Decimal
    protein_100g: Decimal | None = None
    carbs_100g: Decimal | None = None
    fat_100g: Decimal | None = None
    sugars_100g: Decimal | None = None
    food_group: str | None = None
    nova_group: int | None = None


@dataclass(frozen=True, slots=True)
class Intake:
    kcal: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    entries: int
    # False when any entry's food has an unknown macro (its share is missing from the sums).
    macros_complete: bool
    # Known sugar values only (ADR 0032); not part of `macros_complete`.
    sugars_g: Decimal = Decimal(0)
    # The part of `sugars_g` that counts toward SUGAR_LIMIT_G (`sugar.counts_as_free_sugar`).
    free_sugars_g: Decimal = Decimal(0)


def per_grams(per_100g: Decimal, grams: Decimal) -> Decimal:
    return per_100g * grams / 100


def intake(entries: Iterable[IntakeEntry]) -> Intake:
    kcal = protein = carbs = fat = sugars = free_sugars = Decimal(0)
    count = 0
    complete = True
    for e in entries:
        count += 1
        kcal += per_grams(e.kcal_100g, e.grams)
        complete = complete and None not in (e.protein_100g, e.carbs_100g, e.fat_100g)
        protein += per_grams(e.protein_100g or Decimal(0), e.grams)
        carbs += per_grams(e.carbs_100g or Decimal(0), e.grams)
        fat += per_grams(e.fat_100g or Decimal(0), e.grams)
        sugar = per_grams(e.sugars_100g or Decimal(0), e.grams)
        sugars += sugar
        if counts_as_free_sugar(e.food_group, e.nova_group):
            free_sugars += sugar
    return Intake(
        tenth(kcal),
        tenth(protein),
        tenth(carbs),
        tenth(fat),
        count,
        complete,
        tenth(sugars),
        tenth(free_sugars),
    )


# ---------------------------------------------------------------- balance


@dataclass(frozen=True, slots=True)
class Balance:
    exercise_kcal: Decimal  # sum of the activities whose energy is known
    exercise_unknown: int  # activities without a known energy
    expenditure_kcal: Decimal | None  # baseline + known exercise; None without a baseline
    balance_kcal: Decimal | None  # intake - expenditure; None without a baseline
    # True only with a baseline and every activity's energy known.
    complete: bool


def balance(
    intake_kcal: Decimal, baseline: Decimal | None, exercise: Sequence[ActivityEnergy]
) -> Balance:
    """`intake - (baseline + exercise)`; unknown exercise is left out and flagged."""
    known = sum((a.kcal for a in exercise if a.kcal is not None), Decimal(0))
    unknown = sum(1 for a in exercise if not a.known)
    if baseline is None:
        return Balance(known, unknown, None, None, complete=False)
    expenditure = baseline + known
    return Balance(known, unknown, expenditure, intake_kcal - expenditure, complete=unknown == 0)
