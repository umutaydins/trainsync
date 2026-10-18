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
        Key.NO_ASSISTANT: ("I only understand commands for now.\n\n{help}",),
        Key.UNKNOWN_COMMAND: ("Unknown command /{command}. Everything I can do: /help",),
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
        Key.TODAY_NO_PROGRAM: (
            "No active program. Create one on the web, or log freely with /log.",
        ),
        Key.TODAY_TITLE: ("Today: {program} · {day_name}",),
        Key.TODAY_EXERCISE: ("• {name}: {plan} · {suggested}",),
        Key.TODAY_IN_PROGRESS: ("In progress: {count} sets logged.",),
        Key.TODAY_FOOTER: ("Log with /log, finish with /done.",),
        Key.USAGE_PLATES: ("Usage: /plates 102.5",),
        Key.PLATES: ("{target}: {per_side} per side (bar {bar})",),
        Key.PLATES_NONE: ("just the bar",),
        Key.PLATES_INEXACT: ("Closest possible: {achieved} ({difference} short).",),
        Key.USAGE_LOG: ("Usage: /log bench 80x5x3 (also 80x5,5,4 or bw x12x3)",),
        Key.LOG_UNKNOWN_EXERCISE: ('I don\'t know an exercise called "{query}".',),
        Key.LOG_CHOOSE_EXERCISE: ("Which exercise? Reply with a number:\n{choices}",),
        Key.LOG_SAVED: ("Logged {exercise}: {sets}. Workout volume {volume}.",),
        Key.DONE_NO_WORKOUT: ("No open workout today.",),
        Key.DONE_SUMMARY: (
            "Workout done: {count} sets · {exercises} exercises · {volume} · {duration}",
        ),
        Key.PRS_TITLE: ("New records:",),
        Key.PR_WEIGHT_FOR_REPS: ("🏆 {exercise}: {load} x {reps}",),
        Key.PR_E1RM: ("🏆 {exercise}: e1RM {value}",),
        Key.PR_VOLUME: ("🏆 {exercise}: session volume {value}",),
        Key.CHECKIN_PROMPT: ("Daily check-in: did you train today?",),
        Key.CHECKIN_REMINDER: ("Reminder: today's check-in is still open. Did you train today?",),
        Key.CHECKIN_BTN_DONE: ("✅ Done",),
        Key.CHECKIN_BTN_PARTIAL: ("🟡 Partly",),
        Key.CHECKIN_BTN_SKIPPED: ("❌ Skipped",),
        Key.CHECKIN_BTN_REST: ("😴 Rest day",),
        Key.CHECKIN_BTN_SICK: ("🤕 Sick/injured",),
        Key.CHECKIN_BTN_AS_PLANNED: ("As planned",),
        Key.CHECKIN_BTN_STEP: ("{step}",),
        Key.CHECKIN_BTN_SKIP_EXERCISE: ("Skip exercise",),
        Key.CHECKIN_BTN_FINISH: ("Finish",),
        Key.CHECKIN_BTN_EDIT: ("✏️ Edit",),
        Key.CHECKIN_EXERCISE: (
            "{index}/{total} {name}\nPlan: {plan} · {suggested}\n"
            "Tap a button or type 80x5x3, 80x5,5,4 or bw x12x3.",
        ),
        Key.CHECKIN_SETS_SAVED: ("Saved {name}: {sets}.",),
        Key.CHECKIN_EXERCISE_SKIPPED: ("Skipped {name}.",),
        Key.CHECKIN_ALREADY_LOGGED: ("{name}: already logged today ({sets}).",),
        Key.CHECKIN_ASK_FREEFORM: (
            "What did you do? One exercise per message, like /log: bench 80x5x3. "
            "Tap Finish when you're done.",
        ),
        Key.CHECKIN_INVALID_SETS: (
            "I couldn't read that. Type 80x5x3, 80x5,5,4 or bw x12x3, or tap a button.",
        ),
        Key.CHECKIN_ASK_REASON: ("What got in the way? A few words, or tap Skip.",),
        Key.CHECKIN_REASON_SAVED: ("Noted, thanks.",),
        Key.CHECKIN_SKIPPED_NO_REASON: ("Noted.",),
        Key.CHECKIN_REST_SAVED: ("Rest day noted. Recovery is part of training.",),
        Key.CHECKIN_SICK_SAVED: ("Noted. Take care of yourself; training can wait.",),
        Key.CHECKIN_SUMMARY: ("Check-in saved for {day}: {status}",),
        Key.CHECKIN_SUMMARY_WORKOUT: ("Workout: {count} sets · {volume}",),
        Key.CHECKIN_SUMMARY_STREAK: ("Check-in streak: {days} days",),
        Key.CHECKIN_STALE: (
            "That button belongs to an earlier question. Send /report to start the check-in again.",
        ),
        # Coach (P6.11, ADR 0030).
        Key.COACH_REMINDER_BEFORE: ("Workout in 30 minutes: {day}, {time}.",),
        Key.COACH_REMINDER_NOW: ("Time for {day} ({time}).",),
        Key.COACH_NUDGE: ("{day} was planned for {time}. There is still time today.",),
        Key.COACH_MISSED: ("No workout today; {day} was planned. Tomorrow is a new day.",),
        Key.COACH_WORKOUT_START: ("Workout started: {day}. Have a good session.",),
        Key.COACH_REST_OVER: ("Rest is over: next set.",),
        Key.COACH_UNDER_TARGET: ("{exercise}: {done}, planned {target}.",),
        Key.COACH_DONE_GOOD: ("Every planned set done. Well done.",),
        Key.COACH_DONE_BAD: ("{missing} planned sets were not done.",),
        Key.COACH_SOFT_ON: ("Soft mode for 24 hours. /sert turns it off.",),
        Key.COACH_SOFT_OFF: ("Soft mode off.",),
        Key.LANG_CHOOSE: ("Choose the bot's language.",),
        Key.LANG_SET: ("Language set: English.",),
        Key.LANG_USAGE: ("Usage: /lang, /lang en or /lang tr.",),
        Key.SWEAR_CHOOSE: (
            "Profanity in savage mode: max (every message) or roast (only the roasts)?",
        ),
        Key.SWEAR_SET_MAX: ("Profanity: max. It applies while the savage coach is on.",),
        Key.SWEAR_SET_ROAST: ("Profanity: roast. Only the roasts swear.",),
        Key.SWEAR_USAGE: ("Usage: /swear, /swear max or /swear roast.",),
        Key.HELP_POINTER: ("Everything I can do: /help",),
        Key.COACH_FACT_SESSION: ("{day} · {time}",),
        Key.COACH_FACT_UNDER: ("{exercise}: {done}, target {target}.",),
        Key.COACH_FACT_MISSING: ("{missing} planned sets missing.",),
        Key.COACH_ACTION_PLANNED: ("Today: {day}, {time}.",),
        Key.COACH_ACTION_FALLBACK: ("Today: a 20-minute walk, now.",),
        Key.COACH_FREE_WORKOUT: ("free workout",),
    },
)
