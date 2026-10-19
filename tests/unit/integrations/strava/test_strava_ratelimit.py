from datetime import UTC, datetime

import pytest

from trainsync.integrations.strava.ratelimit import (
    next_daily_reset,
    next_window_reset,
    parse_rate_limit,
)


def test_parses_overall_headers() -> None:
    snap = parse_rate_limit({"X-RateLimit-Limit": "200,2000", "X-RateLimit-Usage": "50,300"})
    assert snap is not None
    assert snap.read is None
    assert snap.short_ratio == 0.25
    assert snap.daily_ratio == 0.15


def test_read_limits_raise_the_ratio() -> None:
    snap = parse_rate_limit(
        {
            "x-ratelimit-limit": "200,2000",
            "x-ratelimit-usage": "50,300",
            "x-readratelimit-limit": "100,1000",
            "x-readratelimit-usage": "90,100",
        }
    )
    assert snap is not None
    assert snap.read is not None
    assert snap.short_ratio == 0.9
    assert snap.daily_ratio == 0.15


def test_missing_headers() -> None:
    assert parse_rate_limit({}) is None
    assert parse_rate_limit({"X-RateLimit-Limit": "200,2000"}) is None


@pytest.mark.parametrize(
    ("limit", "usage"),
    [
        ("abc", "1,2"),
        ("200,2000", "abc"),
        ("1", "1,2"),
        ("200,2000", "1"),
        ("0,0", "1,1"),
        ("200,2000", "-1,3"),
        ("1,2,3", "1,2"),
    ],
)
def test_malformed_headers(limit: str, usage: str) -> None:
    assert parse_rate_limit({"X-RateLimit-Limit": limit, "X-RateLimit-Usage": usage}) is None


def test_malformed_read_headers_ignored_but_overall_kept() -> None:
    snap = parse_rate_limit(
        {
            "X-RateLimit-Limit": "200,2000",
            "X-RateLimit-Usage": "10,10",
            "X-ReadRateLimit-Limit": "abc",
            "X-ReadRateLimit-Usage": "1,1",
        }
    )
    assert snap is not None
    assert snap.read is None


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC), datetime(2026, 1, 1, 10, 15, tzinfo=UTC)),
        (datetime(2026, 1, 1, 10, 14, 59, tzinfo=UTC), datetime(2026, 1, 1, 10, 15, tzinfo=UTC)),
        (datetime(2026, 1, 1, 10, 15, 0, tzinfo=UTC), datetime(2026, 1, 1, 10, 30, tzinfo=UTC)),
        (datetime(2026, 1, 1, 23, 50, tzinfo=UTC), datetime(2026, 1, 2, 0, 0, tzinfo=UTC)),
    ],
)
def test_next_window_reset(now: datetime, expected: datetime) -> None:
    assert next_window_reset(now) == expected


def test_next_daily_reset() -> None:
    now = datetime(2026, 1, 31, 23, 59, tzinfo=UTC)
    assert next_daily_reset(now) == datetime(2026, 2, 1, tzinfo=UTC)
