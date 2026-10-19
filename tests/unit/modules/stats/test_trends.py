"""P8.10, ADR 0038: streaks in weeks, the weight trend, adherence planning, buckets, changes."""

from datetime import date, time, timedelta

import pytest

from trainsync.modules.stats.adherence import Adherence, planned
from trainsync.modules.stats.body import moving_averages, slope_per_week
from trainsync.modules.stats.consistency import week_streaks
from trainsync.modules.stats.periods import Bucket, Window
from trainsync.modules.stats.schemas import change
from trainsync.modules.stats.series import bucketize
from trainsync.modules.training.models import Program, ProgramDay, ProgramExercise
from trainsync.modules.training.repository import ProgramTree

MONDAY = date(2026, 10, 19)


def test_training_streak_counts_weeks_and_tolerates_the_week_in_progress() -> None:
    # A Wednesday in each of the three weeks before this one.
    days = {MONDAY - timedelta(7 * n) + timedelta(2) for n in range(1, 4)}
    days |= {date(2026, 8, 3), date(2026, 8, 10)}  # an older run of two
    assert week_streaks(days, MONDAY) == (3, 3)
    assert week_streaks(days | {MONDAY}, MONDAY) == (4, 4)
    assert week_streaks(days, MONDAY + timedelta(7)) == (0, 3)
    assert week_streaks(set(), MONDAY) == (0, 0)


def test_weight_trend() -> None:
    weights = {date(2026, 10, d): 80.0 - 0.1 * d for d in (1, 2, 3, 8)}
    averages = moving_averages(weights)
    assert averages[date(2026, 10, 8)] == pytest.approx((79.8 + 79.7 + 79.2) / 3)
    assert averages[date(2026, 10, 1)] == pytest.approx(79.9)
    points = [(d, w) for d, w in weights.items()]
    assert slope_per_week(points) == pytest.approx(-0.7)
    assert slope_per_week(points[:1]) is None


def _tree(days: list[ProgramDay], sets: int = 3, per_week: int = 3) -> ProgramTree:
    program = Program(name="P", goal="strength", days_per_week=per_week, weeks=4)
    exercise = ProgramExercise(sets=sets, rep_min=5, rep_max=8, rest_seconds=90, exercise_id=1)
    return ProgramTree(program, [(day, [exercise, exercise]) for day in days])


def test_planned_sessions_follow_weekdays_or_days_per_week() -> None:
    days = [
        ProgramDay(id=1, day_index=0, name="A", weekday=0, start_time=time(18)),
        ProgramDay(id=2, day_index=1, name="B", weekday=3, start_time=None),
    ]
    two_weeks = Window(MONDAY, MONDAY + timedelta(13))
    assert planned(_tree(days), two_weeks) == (4, 24)
    unscheduled = [ProgramDay(id=3, day_index=0, name="A", weekday=None)]
    assert planned(_tree(unscheduled, per_week=3), two_weeks) == (6, 36)
    # Two days of a week: at most two of its three sessions are planned.
    assert planned(_tree(unscheduled, per_week=3), Window(MONDAY, MONDAY + timedelta(1))) == (
        2,
        12,
    )


def test_adherence_ratios() -> None:
    plan = Adherence(1, "P", planned_sessions=4, done_sessions=5, planned_sets=0, done_sets=3)
    assert plan.session_ratio == 1.0
    assert plan.set_ratio is None


def test_bucketize_sums_and_means() -> None:
    window = Window(date(2026, 10, 1), date(2026, 10, 14))
    values = {date(2026, 10, 1): 2.0, date(2026, 10, 2): 3.0, date(2026, 10, 13): 5.0}
    sums = bucketize(values, window, Bucket.WEEK, mean=False)
    assert [(p.start, p.value) for p in sums] == [
        (date(2026, 9, 28), 5.0),
        (date(2026, 10, 5), 0),
        (date(2026, 10, 12), 5.0),
    ]
    means = bucketize(values, window, Bucket.WEEK, mean=True)
    assert [p.value for p in means] == [2.5, None, 5.0]


@pytest.mark.parametrize(
    ("value", "previous", "compared", "expected"),
    [
        (12.0, 10.0, True, (2.0, 20.0)),
        (5.0, 0.0, True, (5.0, None)),
        (0.0, 0.0, True, (0.0, None)),
        (None, 3.0, True, (None, None)),
        (4.0, None, False, (None, None)),
    ],
)
def test_change(
    value: float | None,
    previous: float | None,
    compared: bool,
    expected: tuple[float | None, float | None],
) -> None:
    result = change(value, previous, compared)
    assert (result.change, result.change_pct) == expected
    if not compared:
        assert result.previous is None
