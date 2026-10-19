"""Periods of the progress statistics, as inclusive local days (P8.10, ADR 0038).

`week`, `month`, `year` run from the start of the calendar unit to today and compare with the
same number of days at the start of the unit before. `last_week`, `last_month` are whole units
and compare with the unit before. `3m`, `6m`, `12m` and `custom` compare with the same number of
days right before. `all` has no previous period.
"""

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo


class Period(StrEnum):
    WEEK = "week"
    LAST_WEEK = "last_week"
    MONTH = "month"
    LAST_MONTH = "last_month"
    THREE_MONTHS = "3m"
    SIX_MONTHS = "6m"
    YEAR = "year"
    TWELVE_MONTHS = "12m"
    ALL = "all"
    CUSTOM = "custom"


class Bucket(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


ROLLING_MONTHS = {Period.THREE_MONTHS: 3, Period.SIX_MONTHS: 6, Period.TWELVE_MONTHS: 12}
# The smallest bucket that still fits a phone-wide chart (ADR 0038).
DAY_BUCKET_MAX_DAYS = 31
WEEK_BUCKET_MAX_DAYS = 183


@dataclass(frozen=True, slots=True)
class Window:
    """Inclusive local days `start`..`end`."""

    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def bounds(self, zone: ZoneInfo) -> tuple[datetime, datetime]:
        """The UTC instants of the local midnights: `[start 00:00, end + 1 day 00:00)`."""
        return local_midnight(self.start, zone), local_midnight(self.end + timedelta(1), zone)

    def __contains__(self, day: object) -> bool:
        return isinstance(day, date) and self.start <= day <= self.end


@dataclass(frozen=True, slots=True)
class Resolved:
    period: Period
    window: Window
    previous: Window | None


def local_midnight(day: date, zone: ZoneInfo) -> datetime:
    """The instant a local day starts, in UTC (23- and 25-hour DST days included)."""
    return datetime.combine(day, time(0), tzinfo=zone).astimezone(UTC)


def local_today(now: datetime, zone: ZoneInfo) -> date:
    return now.astimezone(zone).date()


def add_months(day: date, months: int) -> date:
    """`day` moved by whole months, clamped to the end of a shorter month (31 Mar - 1 = 28 Feb)."""
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    last = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(day.day, last))


def _before(window: Window) -> Window:
    """The same number of days right before `window`."""
    end = window.start - timedelta(1)
    return Window(end - timedelta(window.days - 1), end)


def _same_span(start: date, days: int, cap: date) -> Window:
    """`days` days from `start`, clamped to `cap` (the end of that calendar unit)."""
    return Window(start, min(start + timedelta(days - 1), cap))


def _calendar(period: Period, today: date) -> Resolved:
    if period in (Period.WEEK, Period.LAST_WEEK):
        monday = today - timedelta(today.weekday())
        if period is Period.LAST_WEEK:
            last = Window(monday - timedelta(7), monday - timedelta(1))
            return Resolved(period, last, _before(last))
        window = Window(monday, today)
        return Resolved(period, window, Window(monday - timedelta(7), today - timedelta(7)))
    if period in (Period.MONTH, Period.LAST_MONTH):
        first = today.replace(day=1)
        previous_first = add_months(first, -1)
        if period is Period.LAST_MONTH:
            last = Window(previous_first, first - timedelta(1))
            before = add_months(previous_first, -1)
            return Resolved(period, last, Window(before, previous_first - timedelta(1)))
        window = Window(first, today)
        return Resolved(
            period, window, _same_span(previous_first, window.days, first - timedelta(1))
        )
    first = today.replace(month=1, day=1)
    previous_first = first.replace(year=first.year - 1)
    window = Window(first, today)
    return Resolved(period, window, _same_span(previous_first, window.days, first - timedelta(1)))


def resolve(
    period: Period,
    today: date,
    *,
    start: date | None = None,
    end: date | None = None,
    first_day: date | None = None,
) -> Resolved:
    """The window of `period` ending on (or before) `today`, and the one it is compared with.

    `start`/`end` are required for `custom`; `first_day` (the user's first data) starts `all`.
    """
    if period is Period.CUSTOM:
        if start is None or end is None:
            raise ValueError("a custom period needs `from` and `to`")
        if end < start:
            raise ValueError("`to` is before `from`")
        window = Window(start, end)
        return Resolved(period, window, _before(window))
    if period is Period.ALL:
        return Resolved(period, Window(min(first_day or today, today), today), None)
    if period in ROLLING_MONTHS:
        window = Window(add_months(today, -ROLLING_MONTHS[period]) + timedelta(1), today)
        return Resolved(period, window, _before(window))
    return _calendar(period, today)


def default_bucket(window: Window) -> Bucket:
    if window.days <= DAY_BUCKET_MAX_DAYS:
        return Bucket.DAY
    if window.days <= WEEK_BUCKET_MAX_DAYS:
        return Bucket.WEEK
    return Bucket.MONTH


def bucket_start(day: date, bucket: Bucket) -> date:
    if bucket is Bucket.WEEK:
        return day - timedelta(day.weekday())
    if bucket is Bucket.MONTH:
        return day.replace(day=1)
    return day


def bucket_starts(window: Window, bucket: Bucket) -> list[date]:
    """Every bucket that overlaps the window, in order (the first may start before it)."""
    starts: list[date] = []
    current = bucket_start(window.start, bucket)
    while current <= window.end:
        starts.append(current)
        if bucket is Bucket.MONTH:
            current = add_months(current, 1)
        else:
            current += timedelta(7 if bucket is Bucket.WEEK else 1)
    return starts
