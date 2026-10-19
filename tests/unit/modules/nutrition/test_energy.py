"""P6.4: energy-balance math (pure functions), hand-computed."""

from datetime import date
from decimal import Decimal

import pytest

from trainsync.modules.nutrition.energy import (
    ActivityEnergy,
    IntakeEntry,
    KcalSource,
    activity_kcal,
    age_on,
    balance,
    baseline_kcal,
    bmr_mifflin_st_jeor,
    intake,
    target_warning,
)
from trainsync.modules.nutrition.models import ActivityBaseline, Sex

D = Decimal


def test_mifflin_st_jeor() -> None:
    # 10*80 + 6.25*180 - 5*35 + 5 = 800 + 1125 - 175 + 5
    assert bmr_mifflin_st_jeor(Sex.MALE, D("80"), D("180"), 35) == D("1755.0")
    # 10*62.5 + 6.25*168 - 5*29 - 161 = 625 + 1050 - 145 - 161
    assert bmr_mifflin_st_jeor(Sex.FEMALE, D("62.5"), D("168"), 29) == D("1369.0")
    # 10*71.3 + 6.25*172.5 - 5*40 + 5 = 713 + 1078.125 - 200 + 5 = 1596.125
    assert bmr_mifflin_st_jeor(Sex.MALE, D("71.3"), D("172.5"), 40) == D("1596.1")


def test_age_uses_the_calendar_year_of_the_day() -> None:
    assert age_on(1991, date(2026, 1, 1)) == 35
    assert age_on(1991, date(2026, 12, 31)) == 35


@pytest.mark.parametrize(
    ("baseline", "expected"),
    [
        (ActivityBaseline.SEDENTARY, D("2106.0")),  # 1755 * 1.2
        (ActivityBaseline.LIGHT, D("2413.1")),  # 1755 * 1.375 = 2413.125, half up
        (ActivityBaseline.MODERATE, D("2720.3")),  # 1755 * 1.55 = 2720.25, half up
    ],
)
def test_baseline_multiplier(baseline: ActivityBaseline, expected: Decimal) -> None:
    assert baseline_kcal(D("1755.0"), baseline) == expected


@pytest.mark.parametrize(
    ("sport_type", "raw", "expected"),
    [
        ("Run", {"calories": 420.5}, ActivityEnergy(D("420.5"), KcalSource.CALORIES)),
        ("Ride", {"calories": 700, "kilojoules": 650}, ActivityEnergy(D("700.0"), "calories")),
        ("Ride", {"kilojoules": 650.04}, ActivityEnergy(D("650.0"), KcalSource.KILOJOULES)),
        ("Ride", {"calories": 0, "kilojoules": 650}, ActivityEnergy(D("650.0"), "kilojoules")),
        ("VirtualRide", {"kilojoules": 512}, ActivityEnergy(D("512.0"), "kilojoules")),
        ("Run", {"kilojoules": 512}, ActivityEnergy(None, None)),  # kJ only means work on a bike
        ("Run", {"calories": 0}, ActivityEnergy(None, None)),
        ("WeightTraining", {}, ActivityEnergy(None, None)),
        ("Run", {"calories": "420"}, ActivityEnergy(None, None)),
        ("Run", {"calories": True}, ActivityEnergy(None, None)),
    ],
)
def test_activity_kcal(sport_type: str, raw: dict[str, object], expected: ActivityEnergy) -> None:
    assert activity_kcal(sport_type, raw) == expected


def test_intake_sums_and_flags_unknown_macros() -> None:
    oats = IntakeEntry(D("80"), D("380"), D("13"), D("60"), D("7"))
    cola = IntakeEntry(D("330"), D("42"), None, D("10.6"), D("0"))
    assert intake([oats]).macros_complete
    total = intake([oats, cola])
    # kcal 304 + 138.6; protein 10.4 (+ unknown); carbs 48 + 34.98; fat 5.6 + 0
    assert (total.kcal, total.protein_g, total.carbs_g, total.fat_g) == (
        D("442.6"),
        D("10.4"),
        D("83.0"),
        D("5.6"),
    )
    assert (total.entries, total.macros_complete) == (2, False)
    empty = intake([])
    assert (empty.kcal, empty.entries, empty.macros_complete) == (D("0.0"), 0, True)


def test_intake_sums_known_sugar_only() -> None:
    baklava = IntakeEntry(D("120"), D("430"), D("6"), D("50"), D("23"), sugars_100g=D("30"))
    unknown = IntakeEntry(D("100"), D("100"))
    total = intake([baklava, unknown])
    assert total.sugars_g == D("36.0")
    assert total.macros_complete is False  # sugar is not a macro: only `unknown` makes it so
    assert intake([]).sugars_g == D("0.0")


def test_intake_counts_free_sugar_only_toward_the_limit() -> None:
    apple = IntakeEntry(D("600"), D("52"), sugars_100g=D("10.4"), food_group="fruit", nova_group=1)
    yoghurt = IntakeEntry(
        D("500"), D("61"), sugars_100g=D("4.7"), food_group="plain_dairy", nova_group=4
    )
    cola = IntakeEntry(
        D("330"), D("42"), sugars_100g=D("10.6"), food_group="sugary_drink", nova_group=4
    )
    bar = IntakeEntry(D("50"), D("400"), sugars_100g=D("15"), nova_group=4)
    total = intake([apple, yoghurt, cola, bar])
    assert total.sugars_g == D("128.4")
    assert total.free_sugars_g == D("42.5")  # cola 35.0 + bar 7.5
    assert intake([apple, yoghurt]).free_sugars_g == D("0.0")


def test_balance_leaves_unknown_exercise_out_and_flags_it() -> None:
    run = ActivityEnergy(D("420.5"), KcalSource.CALORIES)
    gym = ActivityEnergy(None, None)
    full = balance(D("2000.0"), D("2413.1"), [run])
    assert (full.exercise_kcal, full.expenditure_kcal, full.balance_kcal, full.complete) == (
        D("420.5"),
        D("2833.6"),
        D("-833.6"),
        True,
    )
    partial = balance(D("2000.0"), D("2413.1"), [run, gym])
    assert (partial.balance_kcal, partial.exercise_unknown, partial.complete) == (
        D("-833.6"),
        1,
        False,
    )
    no_baseline = balance(D("2000.0"), None, [run])
    assert (no_baseline.expenditure_kcal, no_baseline.balance_kcal) == (None, None)
    assert (no_baseline.exercise_kcal, no_baseline.complete) == (D("420.5"), False)


def test_target_warning_is_neutral_and_only_below_bmr() -> None:
    assert target_warning(None, D("1755.0")) is None
    assert target_warning(1500, None) is None
    assert target_warning(1755, D("1755.0")) is None
    warning = target_warning(1500, D("1755.0"))
    assert warning is not None
    assert "1500" in warning
    assert "1755.0" in warning
    for word in ("too", "should", "unhealthy", "fat", "lose", "danger"):
        assert word not in warning.lower()
