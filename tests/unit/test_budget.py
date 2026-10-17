from datetime import UTC, datetime, timedelta

import pytest

from trainsync.strava.budget import Allowance, BudgetState, Priority, decide

NOW = datetime(2026, 10, 17, 12, 7, tzinfo=UTC)
WINDOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
NEXT_WINDOW = datetime(2026, 10, 17, 12, 15, tzinfo=UTC)
NEXT_DAY = datetime(2026, 10, 18, tzinfo=UTC)


def state(short: float, daily: float = 0.1, window: datetime = WINDOW) -> BudgetState:
    return BudgetState(short_ratio=short, daily_ratio=daily, window_start=window)


def test_no_snapshot_allows_both() -> None:
    assert decide(None, None, "high", NOW) == Allowance(True)
    assert decide(None, None, "low", NOW) == Allowance(True)


@pytest.mark.parametrize(
    ("short", "priority", "expected"),
    [
        (0.79, "low", Allowance(True)),
        (0.80, "low", Allowance(False, NEXT_WINDOW)),
        (0.95, "low", Allowance(False, NEXT_WINDOW)),
        (0.95, "high", Allowance(True)),
        (0.99, "high", Allowance(True)),
        (1.00, "high", Allowance(False, NEXT_WINDOW)),
    ],
)
def test_short_window_threshold(short: float, priority: Priority, expected: Allowance) -> None:
    assert decide(state(short), None, priority, NOW) == expected


def test_stale_snapshot_from_previous_window_is_ignored() -> None:
    previous = state(1.0, window=WINDOW - timedelta(minutes=15))
    assert decide(previous, None, "low", NOW) == Allowance(True)
    assert decide(previous, None, "high", NOW) == Allowance(True)


def test_daily_threshold_pauses_low_until_midnight() -> None:
    assert decide(state(0.1, daily=0.8), None, "low", NOW) == Allowance(False, NEXT_DAY)
    assert decide(state(0.1, daily=0.8), None, "high", NOW) == Allowance(True)


def test_daily_exhaustion_stops_high_too() -> None:
    assert decide(state(0.1, daily=1.0), None, "high", NOW) == Allowance(False, NEXT_DAY)


def test_daily_ratio_from_earlier_window_same_day_still_counts() -> None:
    earlier = state(0.9, daily=0.85, window=WINDOW - timedelta(hours=2))
    assert decide(earlier, None, "low", NOW) == Allowance(False, NEXT_DAY)


def test_daily_ratio_from_yesterday_is_ignored() -> None:
    yesterday = state(0.9, daily=0.99, window=WINDOW - timedelta(days=1))
    assert decide(yesterday, None, "low", NOW) == Allowance(True)


def test_both_limits_resume_at_the_later_reset() -> None:
    assert decide(state(0.9, daily=0.9), None, "low", NOW) == Allowance(False, NEXT_DAY)


@pytest.mark.parametrize("priority", ["high", "low"])
def test_after_429_both_priorities_wait(priority: Priority) -> None:
    assert decide(None, NEXT_WINDOW, priority, NOW) == Allowance(False, NEXT_WINDOW)
    assert decide(state(0.1), NEXT_WINDOW, priority, NOW) == Allowance(False, NEXT_WINDOW)


def test_block_expires() -> None:
    assert decide(None, NOW - timedelta(seconds=1), "low", NOW) == Allowance(True)
    assert decide(None, NOW, "low", NOW) == Allowance(True)


def test_custom_threshold() -> None:
    assert decide(state(0.5), None, "low", NOW, low_priority_threshold=0.5).allowed is False
