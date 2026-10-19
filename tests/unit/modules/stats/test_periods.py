"""P8.10, ADR 0038: periods, their previous periods and buckets."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from trainsync.modules.stats.periods import (
    Bucket,
    Period,
    Window,
    add_months,
    bucket_starts,
    default_bucket,
    local_midnight,
    local_today,
    resolve,
)

TODAY = date(2026, 10, 19)  # a Monday
BERLIN = ZoneInfo("Europe/Berlin")


def w(start: str, end: str) -> Window:
    return Window(date.fromisoformat(start), date.fromisoformat(end))


@pytest.mark.parametrize(
    ("period", "window", "previous"),
    [
        (Period.WEEK, w("2026-10-19", "2026-10-19"), w("2026-10-12", "2026-10-12")),
        (Period.LAST_WEEK, w("2026-10-12", "2026-10-18"), w("2026-10-05", "2026-10-11")),
        (Period.MONTH, w("2026-10-01", "2026-10-19"), w("2026-09-01", "2026-09-19")),
        (Period.LAST_MONTH, w("2026-09-01", "2026-09-30"), w("2026-08-01", "2026-08-31")),
        (Period.THREE_MONTHS, w("2026-07-20", "2026-10-19"), w("2026-04-19", "2026-07-19")),
        (Period.SIX_MONTHS, w("2026-04-20", "2026-10-19"), w("2025-10-19", "2026-04-19")),
        (Period.YEAR, w("2026-01-01", "2026-10-19"), w("2025-01-01", "2025-10-19")),
        (Period.TWELVE_MONTHS, w("2025-10-20", "2026-10-19"), w("2024-10-20", "2025-10-19")),
    ],
)
def test_periods_and_what_they_compare_with(
    period: Period, window: Window, previous: Window
) -> None:
    resolved = resolve(period, TODAY)
    assert (resolved.window, resolved.previous) == (window, previous)


def test_rolling_and_custom_periods_compare_with_the_same_number_of_days() -> None:
    for period in (Period.THREE_MONTHS, Period.SIX_MONTHS, Period.TWELVE_MONTHS):
        resolved = resolve(period, TODAY)
        assert resolved.previous is not None
        assert resolved.previous.days == resolved.window.days
        assert resolved.previous.end == resolved.window.start - timedelta(1)
    custom = resolve(Period.CUSTOM, TODAY, start=date(2026, 3, 1), end=date(2026, 3, 10))
    assert custom.previous == w("2026-02-19", "2026-02-28")


def test_to_date_periods_clamp_to_the_shorter_previous_unit() -> None:
    """31 March: the month before has 28 days. 29 Feb: the same 60 days at the start of the year
    before end on 1 March."""
    march = resolve(Period.MONTH, date(2026, 3, 31))
    assert march.previous == w("2026-02-01", "2026-02-28")
    leap = resolve(Period.YEAR, date(2028, 2, 29))
    assert leap.previous == w("2027-01-01", "2027-03-01")


def test_all_starts_at_the_first_data_and_has_nothing_to_compare_with() -> None:
    resolved = resolve(Period.ALL, TODAY, first_day=date(2023, 5, 2))
    assert resolved.window == w("2023-05-02", "2026-10-19")
    assert resolved.previous is None
    assert resolve(Period.ALL, TODAY).window == w("2026-10-19", "2026-10-19")


def test_custom_needs_both_ends_in_order() -> None:
    with pytest.raises(ValueError, match="needs"):
        resolve(Period.CUSTOM, TODAY, start=TODAY)
    with pytest.raises(ValueError, match="before"):
        resolve(Period.CUSTOM, TODAY, start=TODAY, end=date(2026, 1, 1))


def test_add_months_clamps_to_the_end_of_the_month() -> None:
    assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)


@pytest.mark.parametrize(
    ("days", "bucket"), [(1, Bucket.DAY), (31, Bucket.DAY), (32, Bucket.WEEK), (183, Bucket.WEEK)]
)
def test_default_bucket(days: int, bucket: Bucket) -> None:
    start = date(2026, 1, 1)
    window = Window(start, date.fromordinal(start.toordinal() + days - 1))
    assert default_bucket(window) is bucket
    assert default_bucket(w("2026-01-01", "2026-12-31")) is Bucket.MONTH


def test_buckets_cover_the_window() -> None:
    window = w("2026-10-01", "2026-10-19")
    assert bucket_starts(window, Bucket.WEEK)[0] == date(2026, 9, 28)
    assert len(bucket_starts(window, Bucket.WEEK)) == 4
    assert bucket_starts(w("2025-11-15", "2026-02-01"), Bucket.MONTH) == [
        date(2025, 11, 1),
        date(2025, 12, 1),
        date(2026, 1, 1),
        date(2026, 2, 1),
    ]
    assert len(bucket_starts(window, Bucket.DAY)) == 19


def test_local_midnights_across_a_dst_change() -> None:
    """25 Oct 2026 has 25 hours in Berlin: the day starts at 22:00 UTC, the next at 23:00 UTC."""
    start, end = w("2026-10-25", "2026-10-25").bounds(BERLIN)
    assert start == datetime(2026, 10, 24, 22, tzinfo=UTC)
    assert end == datetime(2026, 10, 25, 23, tzinfo=UTC)
    assert local_midnight(date(2026, 3, 29), BERLIN) == datetime(2026, 3, 28, 23, tzinfo=UTC)
    assert local_today(datetime(2026, 10, 25, 22, 30, tzinfo=UTC), BERLIN) == date(2026, 10, 25)
    assert local_today(datetime(2026, 10, 25, 23, 30, tzinfo=UTC), BERLIN) == date(2026, 10, 26)
