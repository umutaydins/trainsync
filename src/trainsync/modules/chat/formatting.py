"""Message formatting: pure functions from read-API models to plain-text Telegram messages.

Plain text (no parse_mode), so activity names never need escaping. Metric units throughout;
dates are UTC, like the API. This module computes the numbers; the words around them come from
the message pack in `msg` (ADR 0016).
"""

from datetime import date, datetime, timedelta
from enum import StrEnum

from trainsync.modules.activities.router import ActivityOut
from trainsync.modules.coach.packs import Key, Messages
from trainsync.modules.stats.router import StatsSummary, TotalsOut, Week
from trainsync.modules.sync.router import SyncStatusOut

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
# The coach's week verdict compares moving time, so mixed sports count fairly (ADR 0016).
PUSH_BELOW = 0.5
UP_FROM = 1.0


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


def totals_line(totals: TotalsOut, msg: Messages) -> str:
    return msg(
        Key.TOTALS,
        count=totals.count,
        noun=msg(Key.ACTIVITY_ONE if totals.count == 1 else Key.ACTIVITY_MANY),
        distance=km(totals.distance_m),
        time=duration(totals.moving_time_s),
        elevation=elevation(totals.elevation_gain_m),
    )


def day_range(start: date, end: date, msg: Messages) -> str:
    if start == end:
        return msg.day(start)
    if start.month == end.month and start.year == end.year:
        return f"{start.day}-{msg.day(end)}"
    return f"{msg.day(start)} - {msg.day(end)}"


def freshness(last_synced_at: datetime | None, now: datetime, msg: Messages) -> str | None:
    """A warning line when the data is missing or stale, else None."""
    if last_synced_at is None:
        return msg(Key.FRESH_NEVER)
    if now - last_synced_at > STALE_AFTER:
        return msg(Key.FRESH_STALE, when=msg.day_time(last_synced_at))
    return None


def _with_freshness(
    lines: list[str], last_synced_at: datetime | None, now: datetime, msg: Messages
) -> str:
    note = freshness(last_synced_at, now, msg)
    return "\n".join([*lines, note] if note else lines)


def _by_sport(summary: StatsSummary) -> list[str]:
    return [
        f"{sport_emoji(s.sport_type)} {s.sport_type}: {s.count} · {km(s.distance_m)} · "
        f"{duration(s.moving_time_s)}"
        for s in summary.by_sport
    ]


class Verdict(StrEnum):
    PUSH = "push"
    STEADY = "steady"
    UP = "up"
    ZERO_STREAK = "zero_streak"


_VERDICT_KEYS = {
    Verdict.PUSH: Key.VERDICT_PUSH,
    Verdict.STEADY: Key.VERDICT_STEADY,
    Verdict.UP: Key.VERDICT_UP,
    Verdict.ZERO_STREAK: Key.VERDICT_ZERO_STREAK,
}


def week_verdict(this_week: TotalsOut, last_week: TotalsOut) -> tuple[Verdict, int] | None:
    """(verdict, this week's moving time as a % of last week's). Two empty weeks in a row ask
    about injury or rest instead of pushing; below 50% pushes; 100% and up acknowledges and
    raises the bar. None when there is nothing to compare (activities without moving time)."""
    if not this_week.count and not last_week.count:
        return Verdict.ZERO_STREAK, 0
    if last_week.moving_time_s <= 0:
        return (Verdict.UP, 100) if this_week.moving_time_s > 0 else None
    ratio = this_week.moving_time_s / last_week.moving_time_s
    if ratio < PUSH_BELOW:
        return Verdict.PUSH, int(ratio * 100)  # floor: 49.6% still reads as under half
    if ratio >= UP_FROM:
        return Verdict.UP, round(ratio * 100)
    return Verdict.STEADY, int(ratio * 100)


def format_week(
    this_week: StatsSummary, last_week: StatsSummary, now: datetime, msg: Messages
) -> str:
    lines = [msg(Key.WEEK_THIS, range=day_range(this_week.start, this_week.end, msg))]
    if this_week.totals.count:
        lines.append(totals_line(this_week.totals, msg))
        lines.extend(_by_sport(this_week))
    else:
        lines.append(msg(Key.WEEK_NONE_YET))
    lines.append("")
    lines.append(msg(Key.WEEK_LAST, range=day_range(last_week.start, last_week.end, msg)))
    lines.append(
        totals_line(last_week.totals, msg) if last_week.totals.count else msg(Key.WEEK_NONE)
    )
    delta = this_week.totals.distance_m - last_week.totals.distance_m
    if last_week.totals.count or this_week.totals.count:
        lines.append("")
        lines.append(msg(Key.WEEK_DELTA, delta=_signed_km(delta)))
    verdict = week_verdict(this_week.totals, last_week.totals)
    if verdict is not None:
        kind, percent = verdict
        line = msg(_VERDICT_KEYS[kind], percent=percent)
        if line:  # the neutral packs have no verdicts
            lines.extend(["", line] if kind is Verdict.ZERO_STREAK else [line])
    return _with_freshness(lines, this_week.last_synced_at, now, msg)


def _signed_km(delta_m: float) -> str:
    sign = "+" if delta_m >= 0 else "-"
    return f"{sign}{abs(delta_m) / 1000:.1f} km"


def activity_lines(activity: ActivityOut, msg: Messages) -> list[str]:
    """Name, then one line of numbers: distance · time · pace/speed · elevation."""
    parts = [km(activity.distance_m), duration(activity.moving_time_s)]
    speed = pace_or_speed(activity.sport_type, activity.distance_m, activity.moving_time_s)
    if speed:
        parts.append(speed)
    parts.append(elevation(activity.elevation_gain_m))
    return [
        f"{sport_emoji(activity.sport_type)} {activity.name}",
        msg(
            Key.ACTIVITY_WHEN, sport=activity.sport_type, when=msg.weekday_time(activity.start_date)
        ),
        " · ".join(parts),
    ]


def format_last(
    activity: ActivityOut | None, last_synced_at: datetime | None, now: datetime, msg: Messages
) -> str:
    if activity is None:
        return _with_freshness([msg(Key.LAST_NONE)], last_synced_at, now, msg)
    lines = activity_lines(activity, msg)
    if activity.average_heartrate is not None:
        lines.append(msg(Key.LAST_HEARTRATE, bpm=f"{activity.average_heartrate:.0f}"))
    return _with_freshness(lines, last_synced_at, now, msg)


def best_week(weeks: list[Week]) -> Week | None:
    """The week with the greatest distance (the latest on a tie); None if all are empty."""
    best: Week | None = None
    for week in weeks:
        if week.count and (best is None or week.distance_m >= best.distance_m):
            best = week
    return best


def format_stats(
    summary: StatsSummary, weeks: list[Week], label: str, now: datetime, msg: Messages
) -> str:
    sport = f" · {summary.sport_type}" if summary.sport_type else ""
    title = msg(
        Key.STATS_TITLE, label=label, sport=sport, range=day_range(summary.start, summary.end, msg)
    )
    lines = [title]
    if not summary.totals.count:
        lines.append(msg(Key.STATS_NONE))
        return _with_freshness(lines, summary.last_synced_at, now, msg)
    lines.append(totals_line(summary.totals, msg))
    if not summary.sport_type:
        lines.extend(_by_sport(summary))
    best = best_week(weeks)
    if best is not None:
        lines.append(
            msg(
                Key.STATS_BEST_WEEK,
                day=msg.day(best.week_start),
                distance=km(best.distance_m),
                time=duration(best.moving_time_s),
            )
        )
    if summary.longest is not None:
        lines.append(
            msg(
                Key.STATS_LONGEST,
                name=summary.longest.name,
                distance=km(summary.longest.distance_m),
                day=msg.day(summary.longest.start_date),
            )
        )
    return _with_freshness(lines, summary.last_synced_at, now, msg)


def ago(moment: datetime, now: datetime, msg: Messages) -> str:
    seconds = max(int((now - moment).total_seconds()), 0)
    if seconds < 60:
        return msg(Key.AGO_NOW)
    if seconds < 3600:
        return msg(Key.AGO_MINUTES, n=seconds // 60)
    if seconds < 86400:
        return msg(Key.AGO_HOURS, n=seconds // 3600)
    return msg(Key.AGO_DAYS, n=seconds // 86400)


def format_status(status: SyncStatusOut, now: datetime, msg: Messages) -> str:
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
        msg(Key.STATUS_NEVER)
        if status.last_synced_at is None
        else msg(Key.STATUS_SYNCED, ago=ago(status.last_synced_at, now, msg))
    )
    parts = [
        f"{'✅' if healthy else '⚠️'} {synced}",
        msg(
            Key.STATUS_WEBHOOKS,
            pending=webhooks.pending,
            failed=webhooks.failed,
            dead=webhooks.dead_letters,
        ),
        msg(Key.STATUS_CIRCUIT, state=status.circuit.state),
    ]
    if status.rate_limit is not None:
        parts.append(
            msg(Key.STATUS_RATE_LIMIT, percent=f"{status.rate_limit.short_ratio * 100:.0f}")
        )
    return " · ".join(parts)


def format_new_activity(activity: ActivityOut, dashboard_url: str, msg: Messages) -> str:
    """The new-activity notification (P5.6)."""
    lines = [msg(Key.NEW_ACTIVITY), *activity_lines(activity, msg)]
    if dashboard_url:
        lines.append(f"{dashboard_url.rstrip('/')}/activities/{activity.id}")
    return "\n".join(lines)
