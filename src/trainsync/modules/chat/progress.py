"""The progress summary in the chat (P8.11, ADR 0038): `/stats week|month|…` and the digests.

Facts first (code-built numbers, the user's language), then one verdict line in the coach's voice:
the mean change of training time, tonnage and active days against the previous period. Gains are
praised, drops roasted in savage — unless the period had sick or injured days: then a calm line in
every tone, and no max opener. Body weight is never part of it (ADR 0030 guardrails).
"""

from dataclasses import dataclass
from enum import StrEnum

from trainsync.modules.chat.common import thousands
from trainsync.modules.chat.formatting import day_range, duration, km
from trainsync.modules.coach.categories import Category
from trainsync.modules.coach.packs import Key, Messages, NeutralKey
from trainsync.modules.coach.voice import CoachVoice
from trainsync.modules.stats.periods import Period
from trainsync.modules.stats.schemas import Change
from trainsync.modules.stats.totals import StatsSummary

GAIN_FROM_PCT = 10.0
DROP_FROM_PCT = -10.0
UP_ARROW, DOWN_ARROW, LEVEL = "▲", "▼", "="

# /stats arguments → (period, title key)
BOT_PERIODS: dict[str, tuple[Period, Key]] = {
    "week": (Period.WEEK, Key.PERIOD_WEEK),
    "month": (Period.MONTH, Key.PERIOD_MONTH),
    "3m": (Period.THREE_MONTHS, Key.PERIOD_3M),
    "6m": (Period.SIX_MONTHS, Key.PERIOD_6M),
    "year": (Period.YEAR, Key.PERIOD_YEAR),
    "all": (Period.ALL, Key.PERIOD_ALL),
}
DEFAULT_BOT_PERIOD = "week"


class Trend(StrEnum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"
    RECOVERY = "recovery"


@dataclass(frozen=True, slots=True)
class Verdict:
    trend: Trend
    percent: int


def trend(summary: StatsSummary) -> Verdict | None:
    """None without a previous period or without anything to compare."""
    if summary.previous is None:
        return None
    changes = [
        c.change_pct
        for c in (
            summary.endurance.totals.moving_time_s,
            summary.strength.tonnage_kg,
            summary.consistency.active_days,
        )
        if c.change_pct is not None
    ]
    if not changes:
        return None
    mean = sum(changes) / len(changes)
    percent = round(abs(mean))
    if mean <= DROP_FROM_PCT:
        down = Trend.RECOVERY if summary.consistency.sick_days else Trend.DOWN
        return Verdict(down, percent)
    return Verdict(Trend.UP if mean >= GAIN_FROM_PCT else Trend.FLAT, percent)


def arrow(change: Change) -> str:
    if change.change_pct is None:
        return ""
    if change.change_pct > 0:
        return f"{UP_ARROW}{round(change.change_pct)}%"
    if change.change_pct < 0:
        return f"{DOWN_ARROW}{round(abs(change.change_pct))}%"
    return LEVEL


def facts(summary: StatsSummary, title: str, msg: Messages) -> list[str]:
    lines = [title]
    endurance, strength = summary.endurance.totals, summary.strength
    count = int(endurance.count.value or 0)
    sessions = int(strength.sessions.value or 0)
    if not count and not sessions:
        lines.append(msg(Key.PROGRESS_NONE))
    if count:
        lines.append(
            msg(
                Key.PROGRESS_ENDURANCE,
                count=count,
                noun=msg(Key.ACTIVITY_ONE if count == 1 else Key.ACTIVITY_MANY),
                distance=km(endurance.distance_m.value or 0),
                time=duration(int(endurance.moving_time_s.value or 0)),
                change=arrow(endurance.moving_time_s),
            ).rstrip()
        )
    if sessions:
        lines.append(
            msg(
                Key.PROGRESS_STRENGTH,
                sessions=sessions,
                sets=int(strength.sets.value or 0),
                tonnage=thousands(strength.tonnage_kg.value or 0),
                change=arrow(strength.tonnage_kg),
            ).rstrip()
        )
    if strength.pr_count.value:
        lines.append(msg(Key.PROGRESS_PRS, count=int(strength.pr_count.value)))
    active = int(summary.consistency.active_days.value or 0)
    if active:
        weeks = summary.consistency.training_streak_weeks
        lines.append(msg(Key.PROGRESS_CONSISTENCY, days=active, weeks=weeks))
    nutrition = summary.nutrition
    if nutrition.avg_kcal.value is not None:
        kcal = round(nutrition.avg_kcal.value)
        if nutrition.kcal_target:
            line = msg.neutral(
                NeutralKey.KCAL_AVERAGE_TARGET, kcal=kcal, target=nutrition.kcal_target
            )
        else:
            line = msg.neutral(NeutralKey.KCAL_AVERAGE, kcal=kcal)
        lines.append(line)
    return lines


VERDICT_KEYS = {
    Trend.UP: Key.PROGRESS_UP,
    Trend.DOWN: Key.PROGRESS_DOWN,
    Trend.FLAT: Key.PROGRESS_FLAT,
}
VERDICT_LINES = {Trend.UP: Category.PROGRESS_UP, Trend.DOWN: Category.PROGRESS_DOWN}


async def verdict_line(verdict: Verdict, msg: Messages, voice: CoachVoice | None) -> str:
    if verdict.trend is Trend.RECOVERY:
        return msg(Key.PROGRESS_RECOVERY)
    key = VERDICT_KEYS[verdict.trend]
    category = VERDICT_LINES.get(verdict.trend)
    if voice is not None and category is not None:
        return await voice.line(category, key, percent=verdict.percent)
    return msg(key, percent=verdict.percent)


async def progress_message(
    summary: StatsSummary, title_key: Key, msg: Messages, voice: CoachVoice | None
) -> str:
    """The whole message: title, facts, the verdict line; savage max puts its opener in front."""
    span = day_range(summary.window.start, summary.window.end, msg)
    if title_key in (Key.DIGEST_WEEK, Key.DIGEST_MONTH):
        title = msg(title_key, range=span)
    else:
        title = msg(Key.PROGRESS_TITLE, label=msg(title_key), range=span)
    lines = facts(summary, title, msg)
    verdict = trend(summary)
    if verdict is not None:
        line = await verdict_line(verdict, msg, voice)
        if line:  # the neutral packs have no verdicts
            lines.extend(["", line])
    text = "\n".join(lines)
    if voice is None or (verdict is not None and verdict.trend is Trend.RECOVERY):
        return text
    return await voice.decorate(text)
