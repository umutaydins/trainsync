"""Parsing of Strava's `X-RateLimit-*` headers and window arithmetic."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from trainsync.core.logging import get_logger

log = get_logger(__name__)

WINDOW = timedelta(minutes=15)
_warned_malformed = False


@dataclass(frozen=True, slots=True)
class Usage:
    short_usage: int
    short_limit: int
    daily_usage: int
    daily_limit: int

    @property
    def short_ratio(self) -> float:
        return self.short_usage / self.short_limit

    @property
    def daily_ratio(self) -> float:
        return self.daily_usage / self.daily_limit


@dataclass(frozen=True, slots=True)
class RateLimitSnapshot:
    overall: Usage
    read: Usage | None = None

    @property
    def short_ratio(self) -> float:
        return max(u.short_ratio for u in self._usages())

    @property
    def daily_ratio(self) -> float:
        return max(u.daily_ratio for u in self._usages())

    def _usages(self) -> list[Usage]:
        return [self.overall] if self.read is None else [self.overall, self.read]


def parse_rate_limit(headers: Mapping[str, str]) -> RateLimitSnapshot | None:
    """Read `X-RateLimit-*` (and `X-ReadRateLimit-*` when present); `None` if absent or bad."""
    lowered = {k.lower(): v for k, v in headers.items()}
    overall = _parse_pair(lowered, "x-ratelimit")
    if overall is None:
        return None
    read = _parse_pair(lowered, "x-readratelimit")
    return RateLimitSnapshot(overall=overall, read=read)


def _parse_pair(headers: Mapping[str, str], prefix: str) -> Usage | None:
    limit_raw = headers.get(f"{prefix}-limit")
    usage_raw = headers.get(f"{prefix}-usage")
    if limit_raw is None or usage_raw is None:
        return None
    limits, usages = _two_ints(limit_raw), _two_ints(usage_raw)
    if limits is None or usages is None or 0 in limits:
        _warn_malformed(prefix)
        return None
    return Usage(
        short_usage=usages[0], short_limit=limits[0], daily_usage=usages[1], daily_limit=limits[1]
    )


def _two_ints(value: str) -> tuple[int, int] | None:
    parts = value.split(",")
    if len(parts) != 2:
        return None
    try:
        first, second = int(parts[0].strip()), int(parts[1].strip())
    except ValueError:
        return None
    if first < 0 or second < 0:
        return None
    return first, second


def _warn_malformed(prefix: str) -> None:
    global _warned_malformed
    if not _warned_malformed:
        _warned_malformed = True
        log.warning("ratelimit_header_malformed", header=prefix)


def window_start(now: datetime) -> datetime:
    """Start of the 15-minute window `now` falls into (UTC quarter hours)."""
    return now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)


def next_window_reset(now: datetime) -> datetime:
    """The next UTC quarter hour (:00/:15/:30/:45) strictly after `now`."""
    return window_start(now) + WINDOW


def next_daily_reset(now: datetime) -> datetime:
    """The next 00:00 UTC strictly after `now`."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(days=1)
