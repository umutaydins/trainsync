"""Message formatting: pure functions from read-API models to plain-text Telegram messages.

Plain text (no parse_mode), so activity names never need escaping. Metric units throughout;
dates are UTC, like the API.
"""

from datetime import date, datetime, timedelta

from trainsync.api.activities import ActivityOut
from trainsync.api.stats import StatsSummary, TotalsOut, Week
from trainsync.api.sync_status import SyncStatusOut

# Data older than this gets an explicit "as of" warning.
STALE_AFTER = timedelta(hours=24)

_EMOJI = {
    "Run": "🏃",
    "TrailRun": "🏃",
    "VirtualRun": "🏃",
    "Walk": "🚶",
    "Hike": "🥾",
    "Ride": "🚴",
    "GravelRide": "🚴",
    "MountainBikeRide": "🚵",
    "VirtualRide": "🚴",
    "EBikeRide": "🚴",
    "Swim": "🏊",
    "Rowing": "🚣",
    "WeightTraining": "🏋️",
    "Workout": "💪",
    "Yoga": "🧘",
    "AlpineSki": "⛷️",
    "NordicSki": "⛷️",
}
_PACE_SPORTS = {"Run", "TrailRun", "VirtualRun", "Walk", "Hike"}
_SWIM_SPORTS = {"Swim"}

HELP = (
    "trainsync bot\n"
    "/week: this week vs last week\n"
    "/last: latest activity\n"
    "/stats [4w|12w|52w] [sport]: totals and best week, e.g. /stats 12w run\n"
    "/status: sync health"
)


def sport_emoji(sport_type: str) -> str:
    return _EMOJI.get(sport_type, "🏅")


def km(distance_m: float) -> str:
    return f"{distance_m / 1000:.1f} km"


def duration(seconds: int) -> str:
    """`1h 05m` from one hour on, else `42m 10s`."""
    hours, rest = divmod(max(seconds, 0), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"


def elevation(meters: float) -> str:
    return f"↑ {meters:.0f} m"


def pace_or_speed(sport_type: str, distance_m: float, moving_time_s: int) -> str | None:
    """min/km for foot sports, min/100 m for swims, km/h otherwise; None without distance."""
    if distance_m <= 0 or moving_time_s <= 0:
        return None
    if sport_type in _PACE_SPORTS:
        return f"{_min_sec(moving_time_s / (distance_m / 1000))} /km"
    if sport_type in _SWIM_SPORTS:
        return f"{_min_sec(moving_time_s / (distance_m / 100))} /100 m"
    return f"{distance_m / 1000 / (moving_time_s / 3600):.1f} km/h"


def _min_sec(seconds: float) -> str:
    total = round(seconds)
    return f"{total // 60}:{total % 60:02d}"


def totals_line(totals: TotalsOut) -> str:
    noun = "activity" if totals.count == 1 else "activities"
    return (
        f"{totals.count} {noun} · {km(totals.distance_m)} · "
        f"{duration(totals.moving_time_s)} · {elevation(totals.elevation_gain_m)}"
    )


def day_range(start: date, end: date) -> str:
    if start == end:
        return start.strftime("%-d %b")
    if start.month == end.month and start.year == end.year:
        return f"{start.day}-{end.strftime('%-d %b')}"
    return f"{start.strftime('%-d %b')} - {end.strftime('%-d %b')}"


def freshness(last_synced_at: datetime | None, now: datetime) -> str | None:
    """A warning line when the data is missing or stale, else None."""
    if last_synced_at is None:
        return "⚠️ No data synced yet."
    if now - last_synced_at > STALE_AFTER:
        return f"⚠️ Data as of {last_synced_at:%-d %b %H:%M} UTC."
    return None


def _with_freshness(lines: list[str], last_synced_at: datetime | None, now: datetime) -> str:
    note = freshness(last_synced_at, now)
    return "\n".join([*lines, note] if note else lines)


def _by_sport(summary: StatsSummary) -> list[str]:
    return [
        f"{sport_emoji(s.sport_type)} {s.sport_type}: {s.count} · {km(s.distance_m)} · "
        f"{duration(s.moving_time_s)}"
        for s in summary.by_sport
    ]


def format_week(this_week: StatsSummary, last_week: StatsSummary, now: datetime) -> str:
    lines = [f"This week ({day_range(this_week.start, this_week.end)})"]
    if this_week.totals.count:
        lines.append(totals_line(this_week.totals))
        lines.extend(_by_sport(this_week))
    else:
        lines.append("No activities yet.")
    lines.append("")
    lines.append(f"Last week ({day_range(last_week.start, last_week.end)})")
    lines.append(totals_line(last_week.totals) if last_week.totals.count else "No activities.")
    delta = this_week.totals.distance_m - last_week.totals.distance_m
    if last_week.totals.count or this_week.totals.count:
        lines.append("")
        lines.append(f"Distance {_signed_km(delta)} vs last week")
    return _with_freshness(lines, this_week.last_synced_at, now)


def _signed_km(delta_m: float) -> str:
    sign = "+" if delta_m >= 0 else "-"
    return f"{sign}{abs(delta_m) / 1000:.1f} km"


def activity_lines(activity: ActivityOut) -> list[str]:
    """Name, then one line of numbers: distance · time · pace/speed · elevation."""
    parts = [km(activity.distance_m), duration(activity.moving_time_s)]
    speed = pace_or_speed(activity.sport_type, activity.distance_m, activity.moving_time_s)
    if speed:
        parts.append(speed)
    parts.append(elevation(activity.elevation_gain_m))
    return [
        f"{sport_emoji(activity.sport_type)} {activity.name}",
        f"{activity.sport_type} · {activity.start_date:%a %-d %b %H:%M} UTC",
        " · ".join(parts),
    ]


def format_last(
    activity: ActivityOut | None, last_synced_at: datetime | None, now: datetime
) -> str:
    if activity is None:
        return _with_freshness(["No activities yet."], last_synced_at, now)
    lines = activity_lines(activity)
    if activity.average_heartrate is not None:
        lines.append(f"♥ {activity.average_heartrate:.0f} bpm avg")
    return _with_freshness(lines, last_synced_at, now)


def best_week(weeks: list[Week]) -> Week | None:
    """The week with the greatest distance (the latest on a tie); None if all are empty."""
    best: Week | None = None
    for week in weeks:
        if week.count and (best is None or week.distance_m >= best.distance_m):
            best = week
    return best


def format_stats(summary: StatsSummary, weeks: list[Week], label: str, now: datetime) -> str:
    sport = f" · {summary.sport_type}" if summary.sport_type else ""
    lines = [f"Last {label}{sport} ({day_range(summary.start, summary.end)})"]
    if not summary.totals.count:
        lines.append("No activities.")
        return _with_freshness(lines, summary.last_synced_at, now)
    lines.append(totals_line(summary.totals))
    if not summary.sport_type:
        lines.extend(_by_sport(summary))
    best = best_week(weeks)
    if best is not None:
        lines.append(
            f"Best week: {best.week_start:%-d %b} · {km(best.distance_m)} · "
            f"{duration(best.moving_time_s)}"
        )
    if summary.longest is not None:
        lines.append(
            f"Longest: {summary.longest.name} · {km(summary.longest.distance_m)} "
            f"({summary.longest.start_date:%-d %b})"
        )
    return _with_freshness(lines, summary.last_synced_at, now)


def ago(moment: datetime, now: datetime) -> str:
    seconds = max(int((now - moment).total_seconds()), 0)
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} d ago"


def format_status(status: SyncStatusOut, now: datetime) -> str:
    """One line: freshness, webhook backlog, breaker, rate-limit usage."""
    webhooks = status.webhooks
    healthy = (
        status.last_synced_at is not None
        and now - status.last_synced_at <= STALE_AFTER
        and status.circuit.state == "closed"
        and webhooks.failed == 0
        and webhooks.dead_letters == 0
    )
    synced = (
        "never synced"
        if status.last_synced_at is None
        else (f"synced {ago(status.last_synced_at, now)}")
    )
    parts = [
        f"{'✅' if healthy else '⚠️'} {synced}",
        f"webhooks {webhooks.pending} pending / {webhooks.failed} failed / "
        f"{webhooks.dead_letters} dead",
        f"Strava circuit {status.circuit.state}",
    ]
    if status.rate_limit is not None:
        parts.append(f"rate limit {status.rate_limit.short_ratio:.0%}")
    return " · ".join(parts)


def format_new_activity(activity: ActivityOut, dashboard_url: str) -> str:
    """The new-activity notification (P5.6)."""
    lines = ["New activity", *activity_lines(activity)]
    if dashboard_url:
        lines.append(f"{dashboard_url.rstrip('/')}/activities/{activity.id}")
    return "\n".join(lines)
