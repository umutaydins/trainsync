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

    # Training commands (P6.8). Units and numbers are computed in code and passed as fields.
    TODAY_NO_PROGRAM = "today.no_program"
    TODAY_TITLE = "today.title"
    TODAY_EXERCISE = "today.exercise"
    TODAY_IN_PROGRESS = "today.in_progress"
    TODAY_FOOTER = "today.footer"
    USAGE_PLATES = "usage.plates"
    PLATES = "plates"
    PLATES_NONE = "plates.none"
    PLATES_INEXACT = "plates.inexact"
    USAGE_LOG = "usage.log"
    LOG_UNKNOWN_EXERCISE = "log.unknown_exercise"
    LOG_CHOOSE_EXERCISE = "log.choose_exercise"
    LOG_SAVED = "log.saved"
    DONE_NO_WORKOUT = "done.no_workout"
    DONE_SUMMARY = "done.summary"
    PRS_TITLE = "prs.title"
    PR_WEIGHT_FOR_REPS = "pr.weight_for_reps"
    PR_E1RM = "pr.e1rm"
    PR_VOLUME = "pr.volume"

    # Daily check-in (P6.9). Rest and sick/injured answers are calm in every tone (ADR 0020).
    CHECKIN_PROMPT = "checkin.prompt"
    CHECKIN_REMINDER = "checkin.reminder"
    CHECKIN_BTN_DONE = "checkin.button.done"
    CHECKIN_BTN_PARTIAL = "checkin.button.partial"
    CHECKIN_BTN_SKIPPED = "checkin.button.skipped"
    CHECKIN_BTN_REST = "checkin.button.rest"
    CHECKIN_BTN_SICK = "checkin.button.sick"
    CHECKIN_BTN_AS_PLANNED = "checkin.button.as_planned"
    CHECKIN_BTN_STEP = "checkin.button.step"
    CHECKIN_BTN_SKIP_EXERCISE = "checkin.button.skip_exercise"
    CHECKIN_BTN_FINISH = "checkin.button.finish"
    CHECKIN_BTN_EDIT = "checkin.button.edit"
    CHECKIN_EXERCISE = "checkin.exercise"
    CHECKIN_SETS_SAVED = "checkin.sets_saved"
    CHECKIN_EXERCISE_SKIPPED = "checkin.exercise_skipped"
    CHECKIN_ALREADY_LOGGED = "checkin.already_logged"
    CHECKIN_ASK_FREEFORM = "checkin.ask_freeform"
    CHECKIN_INVALID_SETS = "checkin.invalid_sets"
    CHECKIN_ASK_REASON = "checkin.ask_reason"
    CHECKIN_REASON_SAVED = "checkin.reason_saved"
    CHECKIN_SKIPPED_NO_REASON = "checkin.skipped_no_reason"
    CHECKIN_REST_SAVED = "checkin.rest_saved"
    CHECKIN_SICK_SAVED = "checkin.sick_saved"
    CHECKIN_SUMMARY = "checkin.summary"
    CHECKIN_SUMMARY_WORKOUT = "checkin.summary.workout"
    CHECKIN_SUMMARY_STREAK = "checkin.summary.streak"
    CHECKIN_STALE = "checkin.stale"

    # Coach (P6.11, ADR 0030): timed messages and their facts, in normal intensity.
    COACH_REMINDER_BEFORE = "coach.reminder_before"
    COACH_REMINDER_NOW = "coach.reminder_now"
    COACH_NUDGE = "coach.nudge"
    COACH_MISSED = "coach.missed"
    COACH_WORKOUT_START = "coach.workout_start"
    COACH_REST_OVER = "coach.rest_over"
    COACH_UNDER_TARGET = "coach.under_target"
    COACH_DONE_GOOD = "coach.done_good"
    COACH_DONE_BAD = "coach.done_bad"
    COACH_SOFT_ON = "coach.soft_on"
    COACH_SOFT_OFF = "coach.soft_off"
    COACH_FACT_SESSION = "coach.fact.session"
    COACH_FACT_UNDER = "coach.fact.under"
    COACH_FACT_MISSING = "coach.fact.missing"
    COACH_ACTION_PLANNED = "coach.action.planned"
    COACH_ACTION_FALLBACK = "coach.action.fallback"
    COACH_FREE_WORKOUT = "coach.free_workout"


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
    Key.TODAY_NO_PROGRAM: _fields(),
    Key.TODAY_TITLE: _fields("program", "day_name"),
    Key.TODAY_EXERCISE: _fields("name", "plan", "suggested"),
    Key.TODAY_IN_PROGRESS: _fields("count"),
    Key.TODAY_FOOTER: _fields(),
    Key.USAGE_PLATES: _fields(),
    Key.PLATES: _fields("target", "per_side", "bar"),
    Key.PLATES_NONE: _fields(),
    Key.PLATES_INEXACT: _fields("achieved", "difference"),
    Key.USAGE_LOG: _fields(),
    Key.LOG_UNKNOWN_EXERCISE: _fields("query"),
    Key.LOG_CHOOSE_EXERCISE: _fields("choices"),
    Key.LOG_SAVED: _fields("exercise", "sets", "volume"),
    Key.DONE_NO_WORKOUT: _fields(),
    Key.DONE_SUMMARY: _fields("count", "exercises", "volume", "duration"),
    Key.PRS_TITLE: _fields(),
    Key.PR_WEIGHT_FOR_REPS: _fields("exercise", "load", "reps"),
    Key.PR_E1RM: _fields("exercise", "value"),
    Key.PR_VOLUME: _fields("exercise", "value"),
    Key.CHECKIN_PROMPT: _fields(),
    Key.CHECKIN_REMINDER: _fields(),
    Key.CHECKIN_BTN_DONE: _fields(),
    Key.CHECKIN_BTN_PARTIAL: _fields(),
    Key.CHECKIN_BTN_SKIPPED: _fields(),
    Key.CHECKIN_BTN_REST: _fields(),
    Key.CHECKIN_BTN_SICK: _fields(),
    Key.CHECKIN_BTN_AS_PLANNED: _fields(),
    Key.CHECKIN_BTN_STEP: _fields("step"),
    Key.CHECKIN_BTN_SKIP_EXERCISE: _fields(),
    Key.CHECKIN_BTN_FINISH: _fields(),
    Key.CHECKIN_BTN_EDIT: _fields(),
    Key.CHECKIN_EXERCISE: _fields("index", "total", "name", "plan", "suggested"),
    Key.CHECKIN_SETS_SAVED: _fields("name", "sets"),
    Key.CHECKIN_EXERCISE_SKIPPED: _fields("name"),
    Key.CHECKIN_ALREADY_LOGGED: _fields("name", "sets"),
    Key.CHECKIN_ASK_FREEFORM: _fields(),
    Key.CHECKIN_INVALID_SETS: _fields(),
    Key.CHECKIN_ASK_REASON: _fields(),
    Key.CHECKIN_REASON_SAVED: _fields(),
    Key.CHECKIN_SKIPPED_NO_REASON: _fields(),
    Key.CHECKIN_REST_SAVED: _fields(),
    Key.CHECKIN_SICK_SAVED: _fields(),
    Key.CHECKIN_SUMMARY: _fields("day", "status"),
    Key.CHECKIN_SUMMARY_WORKOUT: _fields("count", "volume"),
    Key.CHECKIN_SUMMARY_STREAK: _fields("days"),
    Key.CHECKIN_STALE: _fields(),
    Key.COACH_REMINDER_BEFORE: _fields("day", "time"),
    Key.COACH_REMINDER_NOW: _fields("day", "time"),
    Key.COACH_NUDGE: _fields("day", "time"),
    Key.COACH_MISSED: _fields("day"),
    Key.COACH_WORKOUT_START: _fields("day"),
    Key.COACH_REST_OVER: _fields(),
    Key.COACH_UNDER_TARGET: _fields("exercise", "done", "target"),
    Key.COACH_DONE_GOOD: _fields(),
    Key.COACH_DONE_BAD: _fields("missing"),
    Key.COACH_SOFT_ON: _fields(),
    Key.COACH_SOFT_OFF: _fields(),
    Key.COACH_FACT_SESSION: _fields("day", "time"),
    Key.COACH_FACT_UNDER: _fields("exercise", "done", "target"),
    Key.COACH_FACT_MISSING: _fields("missing"),
    Key.COACH_ACTION_PLANNED: _fields("day", "time"),
    Key.COACH_ACTION_FALLBACK: _fields(),
    Key.COACH_FREE_WORKOUT: _fields(),
}

# Answers that stay calm in every tone: no pushing on rest or on being sick or injured
# (tests/unit/test_bot_messages.py checks the hardcore wording of these, too).
RESPECTFUL: frozenset[Key] = frozenset(
    {Key.CHECKIN_REST_SAVED, Key.CHECKIN_SICK_SAVED, Key.CHECKIN_BTN_REST, Key.CHECKIN_BTN_SICK}
)
