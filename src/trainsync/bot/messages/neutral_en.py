"""Neutral tone, English: the bot's original wording."""

from trainsync.bot.messages.keys import Key
from trainsync.bot.messages.pack import MessagePack

PACK = MessagePack(
    tone="neutral",
    lang="en",
    months=("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    weekdays=("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    texts={
        Key.HELP: (
            "trainsync bot\n"
            "/week: this week vs last week\n"
            "/last: latest activity\n"
            "/stats [4w|12w|52w] [sport]: totals and best week, e.g. /stats 12w run\n"
            "/status: sync health",
        ),
        Key.NO_ASSISTANT: ("I only understand commands for now.\n\n{help}",),
        Key.UNKNOWN_COMMAND: ("Unknown command /{command}.\n\n{help}",),
        Key.USAGE_STATS: ("Usage: /stats [4w|12w|52w] [sport], e.g. /stats 12w run",),
        Key.API_DOWN: ("Sorry, I can't reach the trainsync API right now. Try again in a minute.",),
        Key.WEEK_THIS: ("This week ({range})",),
        Key.WEEK_LAST: ("Last week ({range})",),
        Key.WEEK_NONE_YET: ("No activities yet.",),
        Key.WEEK_NONE: ("No activities.",),
        Key.WEEK_DELTA: ("Distance {delta} vs last week",),
        # Neutral reports numbers only: no verdict line.
        Key.VERDICT_PUSH: ("",),
        Key.VERDICT_STEADY: ("",),
        Key.VERDICT_UP: ("",),
        Key.VERDICT_ZERO_STREAK: ("",),
        Key.LAST_NONE: ("No activities yet.",),
        Key.LAST_HEARTRATE: ("♥ {bpm} bpm avg",),
        Key.ACTIVITY_WHEN: ("{sport} · {when} UTC",),
        Key.STATS_TITLE: ("Last {label}{sport} ({range})",),
        Key.STATS_NONE: ("No activities.",),
        Key.STATS_BEST_WEEK: ("Best week: {day} · {distance} · {time}",),
        Key.STATS_LONGEST: ("Longest: {name} · {distance} ({day})",),
        Key.TOTALS: ("{count} {noun} · {distance} · {time} · {elevation}",),
        Key.ACTIVITY_ONE: ("activity",),
        Key.ACTIVITY_MANY: ("activities",),
        Key.FRESH_NEVER: ("⚠️ No data synced yet.",),
        Key.FRESH_STALE: ("⚠️ Data as of {when} UTC.",),
        Key.STATUS_NEVER: ("never synced",),
        Key.STATUS_SYNCED: ("synced {ago}",),
        Key.STATUS_WEBHOOKS: ("webhooks {pending} pending / {failed} failed / {dead} dead",),
        Key.STATUS_CIRCUIT: ("Strava circuit {state}",),
        Key.STATUS_RATE_LIMIT: ("rate limit {percent}%",),
        Key.AGO_NOW: ("just now",),
        Key.AGO_MINUTES: ("{n} min ago",),
        Key.AGO_HOURS: ("{n} h ago",),
        Key.AGO_DAYS: ("{n} d ago",),
        Key.NEW_ACTIVITY: ("New activity",),
        Key.ASSISTANT_RATE_LIMITED: (
            "You've asked a lot this hour. Try again later, or use /week, /stats or /last.",
        ),
        Key.ASSISTANT_TIMED_OUT: (
            "That took too long to work out. Try a simpler question, or /stats.",
        ),
        Key.ASSISTANT_UNAVAILABLE: (
            "I can't answer questions right now. The commands still work: /week, /stats, /last.",
        ),
        Key.ASSISTANT_TOO_MANY_CALLS: (
            "I needed too many lookups for that one. Try narrowing the question.",
        ),
        Key.ASSISTANT_REFUSED: ("I can't help with that one. Ask me about your training.",),
    },
)
