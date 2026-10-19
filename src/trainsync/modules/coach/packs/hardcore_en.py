"""Hardcore tone, English: "Coach", an original tough-love running coach (ADR 0016).

Short, blunt sentences; mild profanity only (damn, hell, crap). Pushes on effort and consistency,
never on the athlete's body, appearance or identity
(tests/unit/modules/coach/packs/test_bot_messages.py checks a blocklist).
"""

from trainsync.modules.coach.packs.keys import Key
from trainsync.modules.coach.packs.neutral_en import PACK as NEUTRAL
from trainsync.modules.coach.packs.pack import MessagePack

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
            "/stats [week|month|3m|6m|year|all]: progress vs the period before\n"
            "/stats 12w run: totals and best week (4w|12w|52w, any sport)\n"
            "/status: sync health\n"
            "/today: today's planned workout\n"
            "/log bench 80x5x3: log sets (also 80x5,5,4 or bw x12x3)\n"
            "/done: finish the workout\n"
            "/plates 102.5: plates per side\n"
            "/report: daily check-in\n"
            "/yumusak: soft coach for 24 h · /sert: back to normal\n"
            "/lang: Türkçe / English\n"
            "/swear: max / roast (savage profanity)",
        ),
        Key.NO_ASSISTANT: ("I don't do small talk. Commands only.\n\n{help}",),
        Key.UNKNOWN_COMMAND: ("/{command}? Not a thing. The real ones: /help",),
        Key.USAGE_STATS: (
            "Wrong. Usage: /stats [week|month|3m|6m|year|all] or /stats [4w|12w|52w] "
            "[sport], e.g. /stats month",
        ),
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
        Key.PROGRESS_TITLE: NEUTRAL.texts[Key.PROGRESS_TITLE],
        Key.PERIOD_WEEK: NEUTRAL.texts[Key.PERIOD_WEEK],
        Key.PERIOD_MONTH: NEUTRAL.texts[Key.PERIOD_MONTH],
        Key.PERIOD_3M: NEUTRAL.texts[Key.PERIOD_3M],
        Key.PERIOD_6M: NEUTRAL.texts[Key.PERIOD_6M],
        Key.PERIOD_YEAR: NEUTRAL.texts[Key.PERIOD_YEAR],
        Key.PERIOD_ALL: NEUTRAL.texts[Key.PERIOD_ALL],
        Key.DIGEST_WEEK: NEUTRAL.texts[Key.DIGEST_WEEK],
        Key.DIGEST_MONTH: NEUTRAL.texts[Key.DIGEST_MONTH],
        Key.PROGRESS_ENDURANCE: NEUTRAL.texts[Key.PROGRESS_ENDURANCE],
        Key.PROGRESS_STRENGTH: NEUTRAL.texts[Key.PROGRESS_STRENGTH],
        Key.PROGRESS_PRS: NEUTRAL.texts[Key.PROGRESS_PRS],
        Key.PROGRESS_CONSISTENCY: NEUTRAL.texts[Key.PROGRESS_CONSISTENCY],
        Key.PROGRESS_NONE: NEUTRAL.texts[Key.PROGRESS_NONE],
        Key.PROGRESS_RECOVERY: NEUTRAL.texts[Key.PROGRESS_RECOVERY],
        Key.PROGRESS_UP: ("More work than before (+{percent}%). That's the way. Keep it up.",),
        Key.PROGRESS_DOWN: ("Down {percent}% from before. Pick it back up, starting today.",),
        Key.PROGRESS_FLAT: ("Steady. Steady is fine, but push a little harder.",),
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
        Key.TODAY_NO_PROGRAM: (
            "No active program. Build one on the web, or just lift and /log it.",
        ),
        Key.TODAY_TITLE: ("Today: {program} · {day_name}. No skipping.",),
        Key.TODAY_EXERCISE: NEUTRAL.texts[Key.TODAY_EXERCISE],
        Key.TODAY_IN_PROGRESS: ("{count} sets in. Keep going.",),
        Key.TODAY_FOOTER: ("Log with /log, finish with /done. Go.",),
        Key.USAGE_PLATES: ("Wrong. Usage: /plates 102.5",),
        Key.PLATES: NEUTRAL.texts[Key.PLATES],
        Key.PLATES_NONE: NEUTRAL.texts[Key.PLATES_NONE],
        Key.PLATES_INEXACT: NEUTRAL.texts[Key.PLATES_INEXACT],
        Key.USAGE_LOG: ("Wrong. Usage: /log bench 80x5x3 (also 80x5,5,4 or bw x12x3)",),
        Key.LOG_UNKNOWN_EXERCISE: ('"{query}"? Never heard of it.',),
        Key.LOG_CHOOSE_EXERCISE: ("Which one? Number, quick:\n{choices}",),
        Key.LOG_SAVED: (
            "Logged {exercise}: {sets}. Volume {volume}. Next set.",
            "{exercise}: {sets} in the bank. Volume {volume}.",
            "Got it. {exercise}: {sets}. Volume {volume}. Keep moving.",
        ),
        Key.DONE_NO_WORKOUT: ("No open workout today. Start one with /log.",),
        Key.DONE_SUMMARY: (
            "Done: {count} sets · {exercises} exercises · {volume} · {duration}. Good work.",
        ),
        Key.PRS_TITLE: ("New records. Hell yes:",),
        Key.PR_WEIGHT_FOR_REPS: NEUTRAL.texts[Key.PR_WEIGHT_FOR_REPS],
        Key.PR_E1RM: NEUTRAL.texts[Key.PR_E1RM],
        Key.PR_VOLUME: NEUTRAL.texts[Key.PR_VOLUME],
        Key.CHECKIN_PROMPT: ("Coach here. Did you train today?",),
        Key.CHECKIN_REMINDER: ("Still waiting on today's report. Did you train?",),
        Key.CHECKIN_BTN_DONE: NEUTRAL.texts[Key.CHECKIN_BTN_DONE],
        Key.CHECKIN_BTN_PARTIAL: NEUTRAL.texts[Key.CHECKIN_BTN_PARTIAL],
        Key.CHECKIN_BTN_SKIPPED: NEUTRAL.texts[Key.CHECKIN_BTN_SKIPPED],
        Key.CHECKIN_BTN_REST: NEUTRAL.texts[Key.CHECKIN_BTN_REST],
        Key.CHECKIN_BTN_SICK: NEUTRAL.texts[Key.CHECKIN_BTN_SICK],
        Key.CHECKIN_BTN_AS_PLANNED: NEUTRAL.texts[Key.CHECKIN_BTN_AS_PLANNED],
        Key.CHECKIN_BTN_STEP: NEUTRAL.texts[Key.CHECKIN_BTN_STEP],
        Key.CHECKIN_BTN_SKIP_EXERCISE: NEUTRAL.texts[Key.CHECKIN_BTN_SKIP_EXERCISE],
        Key.CHECKIN_BTN_FINISH: NEUTRAL.texts[Key.CHECKIN_BTN_FINISH],
        Key.CHECKIN_BTN_EDIT: NEUTRAL.texts[Key.CHECKIN_BTN_EDIT],
        Key.CHECKIN_EXERCISE: NEUTRAL.texts[Key.CHECKIN_EXERCISE],
        Key.CHECKIN_SETS_SAVED: ("Saved {name}: {sets}. Next.",),
        Key.CHECKIN_EXERCISE_SKIPPED: ("Skipped {name}. Noted.",),
        Key.CHECKIN_ALREADY_LOGGED: NEUTRAL.texts[Key.CHECKIN_ALREADY_LOGGED],
        Key.CHECKIN_ASK_FREEFORM: NEUTRAL.texts[Key.CHECKIN_ASK_FREEFORM],
        Key.CHECKIN_INVALID_SETS: (
            "Can't read that. Type 80x5x3, 80x5,5,4 or bw x12x3, or tap a button.",
        ),
        Key.CHECKIN_ASK_REASON: ("Skipped. Why? A few words, or tap Skip.",),
        Key.CHECKIN_REASON_SAVED: ("Noted. Tomorrow counts.",),
        Key.CHECKIN_SKIPPED_NO_REASON: (
            "No reason? Then there's no excuse either. Tomorrow you train.",
            "Skipped without a reason. Damn. Tomorrow, show up.",
            "Nothing to say? Fine. Make tomorrow count.",
        ),
        # Calm in every tone (ADR 0020): no pushing on rest or illness.
        Key.CHECKIN_REST_SAVED: ("Rest day noted. Recovery is part of training.",),
        Key.CHECKIN_SICK_SAVED: ("Noted. Get well first; training can wait.",),
        Key.CHECKIN_SUMMARY: NEUTRAL.texts[Key.CHECKIN_SUMMARY],
        Key.CHECKIN_SUMMARY_WORKOUT: NEUTRAL.texts[Key.CHECKIN_SUMMARY_WORKOUT],
        Key.CHECKIN_SUMMARY_STREAK: ("Check-in streak: {days} days. Don't break it.",),
        Key.CHECKIN_STALE: NEUTRAL.texts[Key.CHECKIN_STALE],
        # Coach (P6.11, ADR 0030).
        Key.COACH_REMINDER_BEFORE: ("30 minutes to {day} ({time}). Get your bag.",),
        Key.COACH_REMINDER_NOW: ("{day}. {time}. Go.",),
        Key.COACH_NUDGE: ("{day} was at {time}. Still nothing. Damn, go now.",),
        Key.COACH_MISSED: ("{day} was today. It didn't happen. Tomorrow you show up.",),
        Key.COACH_WORKOUT_START: ("{day} started. No phone, just sets.",),
        Key.COACH_REST_OVER: ("Rest is over. Next set.",),
        Key.COACH_UNDER_TARGET: ("{exercise}: {done}, target {target}. Fix it on the next set.",),
        Key.COACH_DONE_GOOD: ("Every set done. That's the job. Again next time.",),
        Key.COACH_DONE_BAD: (
            "{missing} planned sets left on the table. Hell, finish them next time.",
        ),
        Key.COACH_SOFT_ON: ("Fine. Soft mode for 24 hours. /sert when you're ready.",),
        Key.COACH_SOFT_OFF: ("Soft mode off. Back to work.",),
        Key.LANG_CHOOSE: ("Pick a language. Then get back to work.",),
        Key.LANG_SET: ("English it is. Same rules, no excuses.",),
        Key.LANG_USAGE: ("/lang, /lang en or /lang tr. Not that hard.",),
        Key.SWEAR_CHOOSE: ("Savage profanity: max, everywhere, or roast, only in the roasts?",),
        Key.SWEAR_SET_MAX: ("Max it is. Counts once the savage coach is on.",),
        Key.SWEAR_SET_ROAST: ("Roast it is. Swearing stays in the roasts.",),
        Key.SWEAR_USAGE: ("/swear, /swear max or /swear roast. Pick one.",),
        Key.HELP_POINTER: ("The real commands: /help",),
        Key.COACH_FACT_SESSION: NEUTRAL.texts[Key.COACH_FACT_SESSION],
        Key.COACH_FACT_UNDER: NEUTRAL.texts[Key.COACH_FACT_UNDER],
        Key.COACH_FACT_MISSING: NEUTRAL.texts[Key.COACH_FACT_MISSING],
        Key.COACH_ACTION_PLANNED: NEUTRAL.texts[Key.COACH_ACTION_PLANNED],
        Key.COACH_ACTION_FALLBACK: NEUTRAL.texts[Key.COACH_ACTION_FALLBACK],
        Key.COACH_FREE_WORKOUT: NEUTRAL.texts[Key.COACH_FREE_WORKOUT],
    },
)
