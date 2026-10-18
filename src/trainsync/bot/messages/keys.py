"""Every user-facing message key and the fields its templates may use.

A pack must define every key (tests/unit/test_bot_messages.py). Templates are `str.format`
strings; a variant may leave a field out but never use one that is not listed here. An empty
template means "no line" (the neutral packs use that for the coach's week verdicts).
"""

from collections.abc import Mapping
from enum import StrEnum


class Key(StrEnum):
    HELP = "help"
    NO_ASSISTANT = "no_assistant"
    UNKNOWN_COMMAND = "unknown_command"
    USAGE_STATS = "usage_stats"
    API_DOWN = "api_down"

    WEEK_THIS = "week.this"
    WEEK_LAST = "week.last"
    WEEK_NONE_YET = "week.none_yet"
    WEEK_NONE = "week.none"
    WEEK_DELTA = "week.delta"
    VERDICT_PUSH = "week.verdict.push"
    VERDICT_STEADY = "week.verdict.steady"
    VERDICT_UP = "week.verdict.up"
    VERDICT_ZERO_STREAK = "week.verdict.zero_streak"

    LAST_NONE = "last.none"
    LAST_HEARTRATE = "last.heartrate"
    ACTIVITY_WHEN = "activity.when"

    STATS_TITLE = "stats.title"
    STATS_NONE = "stats.none"
    STATS_BEST_WEEK = "stats.best_week"
    STATS_LONGEST = "stats.longest"

    TOTALS = "totals"
    ACTIVITY_ONE = "unit.activity_one"
    ACTIVITY_MANY = "unit.activity_many"

    FRESH_NEVER = "freshness.never"
    FRESH_STALE = "freshness.stale"

    STATUS_NEVER = "status.never"
    STATUS_SYNCED = "status.synced"
    STATUS_WEBHOOKS = "status.webhooks"
    STATUS_CIRCUIT = "status.circuit"
    STATUS_RATE_LIMIT = "status.rate_limit"
    AGO_NOW = "ago.now"
    AGO_MINUTES = "ago.minutes"
    AGO_HOURS = "ago.hours"
    AGO_DAYS = "ago.days"

    NEW_ACTIVITY = "new_activity"

    ASSISTANT_RATE_LIMITED = "assistant.rate_limited"
    ASSISTANT_TIMED_OUT = "assistant.timed_out"
    ASSISTANT_UNAVAILABLE = "assistant.unavailable"
    ASSISTANT_TOO_MANY_CALLS = "assistant.too_many_calls"
    ASSISTANT_REFUSED = "assistant.refused"


def _fields(*names: str) -> frozenset[str]:
    return frozenset(names)


FIELDS: Mapping[Key, frozenset[str]] = {
    Key.HELP: _fields(),
    Key.NO_ASSISTANT: _fields("help"),
    Key.UNKNOWN_COMMAND: _fields("command", "help"),
    Key.USAGE_STATS: _fields(),
    Key.API_DOWN: _fields(),
    Key.WEEK_THIS: _fields("range"),
    Key.WEEK_LAST: _fields("range"),
    Key.WEEK_NONE_YET: _fields(),
    Key.WEEK_NONE: _fields(),
    Key.WEEK_DELTA: _fields("delta"),
    Key.VERDICT_PUSH: _fields("percent"),
    Key.VERDICT_STEADY: _fields("percent"),
    Key.VERDICT_UP: _fields(),
    Key.VERDICT_ZERO_STREAK: _fields(),
    Key.LAST_NONE: _fields(),
    Key.LAST_HEARTRATE: _fields("bpm"),
    Key.ACTIVITY_WHEN: _fields("sport", "when"),
    Key.STATS_TITLE: _fields("label", "sport", "range"),
    Key.STATS_NONE: _fields(),
    Key.STATS_BEST_WEEK: _fields("day", "distance", "time"),
    Key.STATS_LONGEST: _fields("name", "distance", "day"),
    Key.TOTALS: _fields("count", "noun", "distance", "time", "elevation"),
    Key.ACTIVITY_ONE: _fields(),
    Key.ACTIVITY_MANY: _fields(),
    Key.FRESH_NEVER: _fields(),
    Key.FRESH_STALE: _fields("when"),
    Key.STATUS_NEVER: _fields(),
    Key.STATUS_SYNCED: _fields("ago"),
    Key.STATUS_WEBHOOKS: _fields("pending", "failed", "dead"),
    Key.STATUS_CIRCUIT: _fields("state"),
    Key.STATUS_RATE_LIMIT: _fields("percent"),
    Key.AGO_NOW: _fields(),
    Key.AGO_MINUTES: _fields("n"),
    Key.AGO_HOURS: _fields("n"),
    Key.AGO_DAYS: _fields("n"),
    Key.NEW_ACTIVITY: _fields(),
    Key.ASSISTANT_RATE_LIMITED: _fields(),
    Key.ASSISTANT_TIMED_OUT: _fields(),
    Key.ASSISTANT_UNAVAILABLE: _fields(),
    Key.ASSISTANT_TOO_MANY_CALLS: _fields(),
    Key.ASSISTANT_REFUSED: _fields(),
}
