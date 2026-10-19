"""P5.5: message formatting against fixed API responses (tests/fixtures/bot_api_responses.json)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tests.support.messages import NEUTRAL_EN as MSG
from trainsync.modules.activities.router import ActivityOut
from trainsync.modules.chat import formatting
from trainsync.modules.stats.router import StatsSummary, WeeklyStats
from trainsync.modules.sync.router import SyncStatusOut

FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "bot_api_responses.json").read_text(encoding="utf-8")
)
NOW = datetime.fromisoformat(FIXTURE["now"])


def summary(name: str) -> StatsSummary:
    return StatsSummary.model_validate(FIXTURE[name])


def activity(name: str, **overrides: object) -> ActivityOut:
    return ActivityOut.model_validate({**FIXTURE[name], **overrides})


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "0m 00s"), (59, "0m 59s"), (3000, "50m 00s"), (3600, "1h 00m"), (7385, "2h 03m")],
)
def test_duration(seconds: int, expected: str) -> None:
    assert formatting.duration(seconds) == expected


@pytest.mark.parametrize(
    ("sport", "distance_m", "moving_s", "expected"),
    [
        ("Run", 10012.5, 3000, "5:00 /km"),
        ("TrailRun", 21097.5, 7200, "5:41 /km"),
        ("Ride", 30100.0, 3720, "29.1 km/h"),
        ("Swim", 1500.0, 1800, "2:00 /100 m"),
        ("WeightTraining", 0.0, 3600, None),
        ("Run", 5000.0, 0, None),
    ],
)
def test_pace_or_speed(sport: str, distance_m: float, moving_s: int, expected: str | None) -> None:
    assert formatting.pace_or_speed(sport, distance_m, moving_s) == expected


def test_units() -> None:
    assert formatting.km(10012.5) == "10.0 km"
    assert formatting.km(0) == "0.0 km"
    assert formatting.elevation(412.4) == "↑ 412 m"
    assert formatting.sport_emoji("Ride") == "🚴"
    assert formatting.sport_emoji("Kitesurf") == "🏅"


def test_week_with_activities() -> None:
    text = formatting.format_week(
        summary("summary_this_week"), summary("summary_last_week"), NOW, MSG
    )
    assert text == (
        "This week (12-15 Oct)\n"
        "3 activities · 41.3 km · 2h 03m · ↑ 412 m\n"
        "🚴 Ride: 1 · 30.1 km · 1h 02m\n"
        "🏃 Run: 2 · 11.2 km · 1h 01m\n"
        "\n"
        "Last week (5-11 Oct)\n"
        "4 activities · 52.0 km · 3h 00m · ↑ 520 m\n"
        "\n"
        "Distance -10.7 km vs last week"
    )


def test_empty_week_and_stale_data() -> None:
    text = formatting.format_week(
        summary("summary_empty_week"), summary("summary_last_week"), NOW, MSG
    )
    assert text == (
        "This week (12-15 Oct)\n"
        "No activities yet.\n"
        "\n"
        "Last week (5-11 Oct)\n"
        "4 activities · 52.0 km · 3h 00m · ↑ 520 m\n"
        "\n"
        "Distance -52.0 km vs last week\n"
        "⚠️ Data as of 10 Oct 08:00 UTC."
    )


def test_two_empty_weeks_have_no_comparison() -> None:
    empty = summary("summary_empty_week")
    last = empty.model_copy(update={"last_synced_at": None})
    text = formatting.format_week(last, empty, NOW, MSG)
    assert "Distance" not in text
    assert text.endswith("No activities.\n⚠️ No data synced yet.")


def test_last_activity() -> None:
    text = formatting.format_last(activity("activity_run"), NOW, NOW, MSG)
    assert text == (
        "🏃 Morning Run\n"
        "Run · Wed 14 Oct 06:30 UTC\n"
        "10.0 km · 50m 00s · 5:00 /km · ↑ 42 m\n"
        "♥ 151 bpm avg"
    )


def test_last_ride_shows_speed_and_no_heartrate() -> None:
    text = formatting.format_last(activity("activity_ride"), NOW, NOW, MSG)
    assert text.splitlines()[1:] == [
        "Ride · Tue 13 Oct 17:00 UTC",
        "30.1 km · 1h 02m · 29.1 km/h · ↑ 350 m",
    ]


def test_last_without_activities() -> None:
    assert (
        formatting.format_last(None, None, NOW, MSG) == "No activities yet.\n⚠️ No data synced yet."
    )


def test_stats_with_best_week_and_longest() -> None:
    weekly = WeeklyStats.model_validate(FIXTURE["weekly_12w_run"])
    text = formatting.format_stats(summary("summary_12w_run"), weekly.weeks, "12w", NOW, MSG)
    assert text == (
        "Last 12w · Run (27 Jul - 15 Oct)\n"
        "30 activities · 301.5 km · 27h 00m · ↑ 2100 m\n"
        "Best week: 14 Sep · 52.0 km · 4h 43m\n"
        "Longest: Long Run · 30.0 km (20 Sep)"
    )


def test_stats_all_sports_lists_each_sport() -> None:
    text = formatting.format_stats(summary("summary_this_week"), [], "4w", NOW, MSG)
    assert text.splitlines() == [
        "Last 4w (12-15 Oct)",
        "3 activities · 41.3 km · 2h 03m · ↑ 412 m",
        "🚴 Ride: 1 · 30.1 km · 1h 02m",
        "🏃 Run: 2 · 11.2 km · 1h 01m",
    ]


def test_stats_empty_range() -> None:
    text = formatting.format_stats(summary("summary_empty_week"), [], "4w", NOW, MSG)
    assert text.splitlines()[:2] == ["Last 4w (12-15 Oct)", "No activities."]


def test_best_week_prefers_latest_on_tie_and_skips_empty() -> None:
    weeks = WeeklyStats.model_validate(FIXTURE["weekly_12w_run"]).weeks
    tie = weeks[1].model_copy(update={"distance_m": 52000.0})
    best = formatting.best_week([weeks[0], tie, weeks[2]])
    assert best is not None
    assert best.week_start == tie.week_start
    assert formatting.best_week([weeks[2]]) is None


def test_status_lines() -> None:
    healthy = SyncStatusOut.model_validate(FIXTURE["sync_status_healthy"])
    degraded = SyncStatusOut.model_validate(FIXTURE["sync_status_degraded"])
    assert formatting.format_status(healthy, NOW, MSG) == (
        "✅ synced 20 min ago · webhooks 0 pending / 0 failed / 0 dead · "
        "Strava circuit closed · rate limit 12%"
    )
    assert formatting.format_status(degraded, NOW, MSG) == (
        "⚠️ synced 3 h ago · webhooks 2 pending / 1 failed / 0 dead · Strava circuit open"
    )
    never = degraded.model_copy(update={"last_synced_at": None})
    assert formatting.format_status(never, NOW, MSG).startswith("⚠️ never synced")


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(5, "just now"), (125, "2 min ago"), (7300, "2 h ago"), (200_000, "2 d ago")],
)
def test_ago(seconds: int, expected: str) -> None:
    moment = datetime(2026, 10, 15, tzinfo=UTC)
    assert formatting.ago(moment, moment.fromtimestamp(moment.timestamp() + seconds, UTC), MSG) == (
        expected
    )


def test_day_range_across_months_and_single_day() -> None:
    first = summary("summary_12w_run")
    assert formatting.day_range(first.start, first.start, MSG) == "27 Jul"


def test_new_activity_message() -> None:
    text = formatting.format_new_activity(activity("activity_run"), "https://dash.example/", MSG)
    assert text == (
        "New activity\n"
        "🏃 Morning Run\n"
        "Run · Wed 14 Oct 06:30 UTC\n"
        "10.0 km · 50m 00s · 5:00 /km · ↑ 42 m\n"
        "https://dash.example/activities/10000000123"
    )
    assert "http" not in formatting.format_new_activity(activity("activity_run"), "", MSG)
