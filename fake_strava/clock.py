"""Clocks: the real one and a manually advanced one for tests."""

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    """A clock that only moves when told to."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = _aware(start or datetime(2026, 10, 17, 12, 0, tzinfo=UTC))

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta | float) -> datetime:
        self._now += delta if isinstance(delta, timedelta) else timedelta(seconds=delta)
        return self._now

    def set(self, value: datetime) -> None:
        self._now = _aware(value)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("FakeClock needs a timezone-aware datetime")
    return value
