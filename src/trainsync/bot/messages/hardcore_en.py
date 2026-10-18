"""Hardcore tone, English: "Coach", an original tough-love running coach (ADR 0016).

Short, blunt sentences; mild profanity only (damn, hell, crap). Pushes on effort and consistency,
never on the athlete's body, appearance or identity (tests/unit/test_bot_messages.py checks a
blocklist).
"""

from trainsync.bot.messages.keys import Key
from trainsync.bot.messages.neutral_en import PACK as NEUTRAL
from trainsync.bot.messages.pack import MessagePack

PACK = MessagePack(
    tone="hardcore",
    lang="en",
    months=NEUTRAL.months,
    weekdays=NEUTRAL.weekdays,
    texts={
        Key.HELP: (
            "Coach here. Commands, no excuses.\n"
            "/week: this week vs last week\n"
            "/last: latest activity\n"
            "/stats [4w|12w|52w] [sport]: totals and best week, e.g. /stats 12w run\n"
            "/status: sync health",
        ),
        Key.NO_ASSISTANT: ("I don't do small talk. Commands only.\n\n{help}",),
        Key.UNKNOWN_COMMAND: ("/{command}? Not a thing.\n\n{help}",),
        Key.USAGE_STATS: ("Wrong. Usage: /stats [4w|12w|52w] [sport], e.g. /stats 12w run",),
        Key.API_DOWN: (
            "Can't reach the trainsync API. Not your fault, for once. Try again in a minute.",
            "The API is down. Go run while it sorts itself out. Try again in a minute.",
            "Hell, the API won't answer. Give it a minute.",
        ),
        Key.WEEK_THIS: ("This week ({range})",),
        Key.WEEK_LAST: ("Last week ({range})",),
        Key.WEEK_NONE_YET: (
            "Nothing yet. The week won't run itself.",
            "Zero so far. Your shoes are by the door.",
            "Empty. Fix that.",
        ),
        Key.WEEK_NONE: ("Nothing.",),
        Key.WEEK_DELTA: ("Distance {delta} vs last week",),
        Key.VERDICT_PUSH: (
            "{percent}% of last week's time. That's not training, that's a rumour. Get out there.",
            "{percent}% of last week's time. Damn. Lace up today, not tomorrow.",
            "Only {percent}% of last week's time. Stop negotiating and go.",
        ),
        Key.VERDICT_STEADY: (
            "{percent}% of last week's time. Close. Finish the job.",
            "{percent}% of last week's time. Not bad. Not done either.",
            "{percent}% of last week's time. Keep stacking days.",
        ),
        Key.VERDICT_UP: (
            "At least last week's time. Good. Next week, a little more.",
            "You kept up with last week. Respect. Now add one session.",
            "Last week's bar is cleared. Hell yes. Don't get comfortable.",
        ),
        Key.VERDICT_ZERO_STREAK: (
            "Two empty weeks. Injured or resting? Tell me which, and we plan around it.",
            "Nothing last week, nothing this week. Is it an injury or a planned break?",
            "Two zero weeks in a row. Hurt, or taking a rest? Be straight with me.",
        ),
        Key.LAST_NONE: (
            "No activities yet. Nothing to judge. Go make some.",
            "Nothing logged. Crap. Start today.",
            "Empty log. One easy run fixes that.",
        ),
        Key.LAST_HEARTRATE: ("♥ {bpm} bpm avg",),
        Key.ACTIVITY_WHEN: ("{sport} · {when} UTC",),
        Key.STATS_TITLE: ("Last {label}{sport} ({range})",),
        Key.STATS_NONE: ("Nothing in this range. Crap.",),
        Key.STATS_BEST_WEEK: ("Best week: {day} · {distance} · {time}. Beat it.",),
        Key.STATS_LONGEST: ("Longest: {name} · {distance} ({day})",),
        Key.TOTALS: NEUTRAL.texts[Key.TOTALS],
        Key.ACTIVITY_ONE: NEUTRAL.texts[Key.ACTIVITY_ONE],
        Key.ACTIVITY_MANY: NEUTRAL.texts[Key.ACTIVITY_MANY],
        Key.FRESH_NEVER: ("⚠️ Nothing synced yet. Connect Strava first.",),
        Key.FRESH_STALE: ("⚠️ Data as of {when} UTC. Old news.",),
        Key.STATUS_NEVER: NEUTRAL.texts[Key.STATUS_NEVER],
        Key.STATUS_SYNCED: NEUTRAL.texts[Key.STATUS_SYNCED],
        Key.STATUS_WEBHOOKS: NEUTRAL.texts[Key.STATUS_WEBHOOKS],
        Key.STATUS_CIRCUIT: NEUTRAL.texts[Key.STATUS_CIRCUIT],
        Key.STATUS_RATE_LIMIT: NEUTRAL.texts[Key.STATUS_RATE_LIMIT],
        Key.AGO_NOW: NEUTRAL.texts[Key.AGO_NOW],
        Key.AGO_MINUTES: NEUTRAL.texts[Key.AGO_MINUTES],
        Key.AGO_HOURS: NEUTRAL.texts[Key.AGO_HOURS],
        Key.AGO_DAYS: NEUTRAL.texts[Key.AGO_DAYS],
        Key.NEW_ACTIVITY: (
            "Logged. Good.",
            "Another session in the bank.",
            "That counts. Recover, then go again.",
            "Done. Don't let it be the last one this week.",
        ),
        Key.ASSISTANT_RATE_LIMITED: (
            "Enough questions for this hour. Go train. /week, /stats and /last still work.",
        ),
        Key.ASSISTANT_TIMED_OUT: ("Too slow. Ask something simpler, or use /stats.",),
        Key.ASSISTANT_UNAVAILABLE: (
            "No questions right now. The commands still work: /week, /stats, /last.",
        ),
        Key.ASSISTANT_TOO_MANY_CALLS: ("Too many lookups for that one. Narrow it down.",),
        Key.ASSISTANT_REFUSED: ("Not my business. Ask about your training.",),
    },
)
