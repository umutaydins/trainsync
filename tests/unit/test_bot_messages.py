"""Message packs (BOT_TONE x BOT_LANG, ADR 0016): completeness, snapshots, the coach's rules and
a wording blocklist.

Snapshots live in tests/unit/snapshots/bot_messages/; regenerate them after a deliberate wording
change with `UPDATE_SNAPSHOTS=1 uv run pytest tests/unit/test_bot_messages.py` and review the diff.
"""

# Turkish words below: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

import json
import os
import random
import re
import string
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import make_settings
from trainsync.api.activities import ActivityOut
from trainsync.api.stats import StatsSummary, TotalsOut, WeeklyStats
from trainsync.api.sync_status import SyncStatusOut
from trainsync.bot import formatting
from trainsync.bot.formatting import Verdict, week_verdict
from trainsync.bot.messages import (
    FIELDS,
    NEUTRAL_FIELDS,
    NEUTRAL_TEXTS,
    PACKS,
    RESPECTFUL,
    Key,
    MessagePack,
    Messages,
    NeutralKey,
    messages_for,
)

FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "bot_api_responses.json").read_text(encoding="utf-8")
)
NOW = datetime.fromisoformat(FIXTURE["now"])
SNAPSHOTS = Path(__file__).parent / "snapshots" / "bot_messages"
SEED = 7
ALL_PACKS = list(PACKS.values())
HARDCORE = [pack for pack in ALL_PACKS if pack.tone == "hardcore"]
pack_ids = pytest.mark.parametrize("pack", ALL_PACKS, ids=[f"{p.tone}-{p.lang}" for p in ALL_PACKS])
hardcore_ids = pytest.mark.parametrize("pack", HARDCORE, ids=[p.lang for p in HARDCORE])

# Words the bot must never say. Profanity stronger than the allowed mild set (damn, hell, crap;
# lan, ulan, hassiktir), insults and slurs, and anything about body, weight or appearance.
BLOCKLIST_EN = re.compile(
    r"\b(fuck\w*|shit\w*|bitch\w*|bastard\w*|cunt\w*|dick\w*|pussy|asshole\w*|whore\w*|slut\w*"
    r"|idiot\w*|moron\w*|stupid\w*|dumb\w*|loser\w*|pathetic|worthless|useless"
    r"|retard\w*|fag\w*|tranny|spaz\w*|cripple\w*"
    r"|fat|fatty|fatso|obese|chubby|skinny|ugly|belly|bellies|weight\w*|weigh\w*|pounds?|lbs|kg"
    r"|body|bodies|appearance|looks?)\b",
    re.IGNORECASE,
)
BLOCKLIST_TR = re.compile(
    r"\b(sik\w*|amk|amına\w*|amcık\w*|orospu\w*|piç\w*|yavşak\w*|göt\w*|pezevenk\w*|kahpe\w*"
    r"|gerizekal\w*|salak\w*|aptal\w*|mal|dangalak\w*|beyinsiz\w*|ezik\w*|işe yaramaz\w*"
    r"|ibne\w*|sakat|özürlü\w*|kötürüm\w*"
    r"|şişko\w*|şişman\w*|obez\w*|kilo|kilolu\w*|kiloyu|kilonu|göbek\w*|zayıf\w*|çirkin\w*"
    r"|vücud\w*|vücut\w*|beden\w*|görünüş\w*|dış görünüş\w*)\b",
    re.IGNORECASE,
)


def summary(name: str, **totals: int) -> StatsSummary:
    base = StatsSummary.model_validate(FIXTURE[name])
    if not totals:
        return base
    return base.model_copy(update={"totals": base.totals.model_copy(update=totals)})


def activity(name: str) -> ActivityOut:
    return ActivityOut.model_validate(FIXTURE[name])


def every_template(pack: MessagePack) -> list[tuple[Key, str]]:
    return [(key, template) for key, variants in pack.texts.items() for template in variants]


def rendered(pack: MessagePack, key: Key) -> set[str]:
    """Every variant of `key` with sample fields, for "is this text one of those" checks."""
    fields: dict[str, object] = dict.fromkeys(FIELDS[key], "?")
    return {template.format(**fields) for template in pack.texts[key]}


# ---------------------------------------------------------------- completeness


@pack_ids
def test_every_pack_defines_every_key(pack: MessagePack) -> None:
    missing = set(Key) - set(pack.texts)
    extra = set(pack.texts) - set(Key)
    assert not missing, f"{pack.tone}/{pack.lang} is missing {sorted(missing)}"
    assert not extra
    assert all(pack.texts[key] for key in Key), "every key needs at least one variant"


def test_every_key_lists_its_fields() -> None:
    assert set(FIELDS) == set(Key)


@pack_ids
def test_templates_only_use_their_keys_fields(pack: MessagePack) -> None:
    for key, template in every_template(pack):
        used = {name for _, name, _, _ in string.Formatter().parse(template) if name}
        assert used <= FIELDS[key], f"{pack.tone}/{pack.lang} {key}: {used - FIELDS[key]}"


@pack_ids
def test_calendar_names(pack: MessagePack) -> None:
    assert len(pack.months) == 12
    assert len(pack.weekdays) == 7


def test_every_tone_and_language_has_a_pack() -> None:
    assert set(PACKS) == {(t, lang) for t in ("neutral", "hardcore") for lang in ("en", "tr")}
    msg = messages_for(make_settings(bot_tone="hardcore", bot_lang="tr"))
    assert (msg.tone, msg.lang) == ("hardcore", "tr")
    default = messages_for(make_settings())
    assert (default.tone, default.lang) == ("neutral", "en")


# ---------------------------------------------------------------- snapshots


def scenarios(msg: Messages) -> dict[str, str]:
    weekly = WeeklyStats.model_validate(FIXTURE["weekly_12w_run"]).weeks
    this_week, last_week = summary("summary_this_week"), summary("summary_last_week")
    empty = summary("summary_empty_week")
    return {
        "help": msg.help(),
        "no assistant": msg(Key.NO_ASSISTANT, help=msg.help()),
        "unknown command": msg(Key.UNKNOWN_COMMAND, command="foo", help=msg.help()),
        "usage": msg(Key.USAGE_STATS),
        "api down": msg(Key.API_DOWN),
        "week, 68% of last week": formatting.format_week(this_week, last_week, NOW, msg),
        "week, nothing yet": formatting.format_week(empty, last_week, NOW, msg),
        "week, beat last week": formatting.format_week(last_week, this_week, NOW, msg),
        "week, two empty weeks": formatting.format_week(empty, empty, NOW, msg),
        "last": formatting.format_last(activity("activity_run"), NOW, NOW, msg),
        "last, none": formatting.format_last(None, None, NOW, msg),
        "stats 12w run": formatting.format_stats(
            summary("summary_12w_run"), weekly, "12w", NOW, msg
        ),
        "stats, empty": formatting.format_stats(empty, [], "4w", NOW, msg),
        "status, healthy": formatting.format_status(
            SyncStatusOut.model_validate(FIXTURE["sync_status_healthy"]), NOW, msg
        ),
        "status, degraded": formatting.format_status(
            SyncStatusOut.model_validate(FIXTURE["sync_status_degraded"]), NOW, msg
        ),
        "new activity": formatting.format_new_activity(
            activity("activity_ride"), "https://dash.example", msg
        ),
        "assistant, rate limited": msg(Key.ASSISTANT_RATE_LIMITED),
        "assistant, timed out": msg(Key.ASSISTANT_TIMED_OUT),
        "assistant, unavailable": msg(Key.ASSISTANT_UNAVAILABLE),
        "assistant, too many calls": msg(Key.ASSISTANT_TOO_MANY_CALLS),
        "assistant, refused": msg(Key.ASSISTANT_REFUSED),
        **training_scenarios(msg),
    }


def training_scenarios(msg: Messages) -> dict[str, str]:
    """Every training and check-in key once, with sample numbers (P6.8, P6.9)."""
    sample: dict[str, object] = {
        "program": "Upper/Lower",
        "day_name": "Upper A",
        "day": "18 Oct",
        "count": 14,
        "name": "Bench Press",
        "exercise": "Bench Press",
        "plan": "3 x 8-12",
        "suggested": "80 kg",
        "sets": "80 kg x 5, 5, 5",
        "target": "102.5 kg",
        "per_side": "25 + 15 + 1.25 kg",
        "bar": "20 kg",
        "achieved": "100 kg",
        "difference": "2.5 kg",
        "query": "zercher",
        "choices": "1. Bench Press\n2. Incline Bench Press",
        "volume": "8,240 kg",
        "exercises": 5,
        "duration": "1h 05m",
        "load": "82.5 kg",
        "reps": 8,
        "value": "96.3 kg",
        "step": "+2.5 kg",
        "index": 2,
        "total": 5,
        "status": "✅",
        "days": 6,
    }
    keys = [key for key in Key if key.value.split(".")[0] in TRAINING_GROUPS]
    return {
        f"{key.value}": msg(key, **{f: sample[f] for f in FIELDS[key] if f in sample})
        for key in keys
    }


TRAINING_GROUPS = {"today", "usage", "plates", "log", "done", "prs", "pr", "checkin"}


def render_snapshot(pack: MessagePack) -> str:
    texts = scenarios(Messages(pack, random.Random(SEED)))
    return "".join(f"## {name}\n{text}\n\n" for name, text in texts.items())


@pack_ids
def test_snapshot(pack: MessagePack) -> None:
    path = SNAPSHOTS / f"{pack.tone}_{pack.lang}.txt"
    actual = render_snapshot(pack)
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
    assert path.exists(), f"missing {path}; run with UPDATE_SNAPSHOTS=1"
    assert actual == path.read_text(encoding="utf-8")


def test_neutral_english_snapshot_is_the_original_wording() -> None:
    text = (SNAPSHOTS / "neutral_en.txt").read_text(encoding="utf-8")
    assert "## week, 68% of last week\nThis week (12-15 Oct)\n" in text
    assert "Distance -10.7 km vs last week\n\n## week, nothing yet" in text


# ---------------------------------------------------------------- the coach's rules


def totals(count: int, moving_time_s: int) -> TotalsOut:
    return TotalsOut(
        count=count, distance_m=moving_time_s * 3.0, moving_time_s=moving_time_s, elevation_gain_m=0
    )


@pytest.mark.parametrize(
    ("this_s", "last_s", "expected"),
    [
        (0, 10_000, (Verdict.PUSH, 0)),
        (4_000, 10_000, (Verdict.PUSH, 40)),
        (4_999, 10_000, (Verdict.PUSH, 49)),
        (5_000, 10_000, (Verdict.STEADY, 50)),
        (9_999, 10_000, (Verdict.STEADY, 99)),
        (10_000, 10_000, (Verdict.UP, 100)),
        (14_600, 10_000, (Verdict.UP, 146)),
        (3_600, 0, (Verdict.UP, 100)),
    ],
)
def test_week_verdict_thresholds(this_s: int, last_s: int, expected: tuple[Verdict, int]) -> None:
    this_week = totals(1 if this_s else 0, this_s)
    last_week = totals(1 if last_s else 0, last_s)
    assert week_verdict(this_week, last_week) == expected


def test_two_empty_weeks_ask_instead_of_pushing() -> None:
    assert week_verdict(totals(0, 0), totals(0, 0)) == (Verdict.ZERO_STREAK, 0)
    # Activities without moving time (manual entries): nothing to compare, no verdict.
    assert week_verdict(totals(0, 0), totals(2, 0)) is None


def week_text(pack: MessagePack, this_s: int, last_s: int, seed: int = SEED) -> str:
    this_week = summary("summary_this_week", count=1 if this_s else 0, moving_time_s=this_s)
    last_week = summary("summary_last_week", count=1 if last_s else 0, moving_time_s=last_s)
    return formatting.format_week(this_week, last_week, NOW, Messages(pack, random.Random(seed)))


def verdict_lines(pack: MessagePack, key: Key, percent: int) -> set[str]:
    return {template.format(percent=percent) for template in pack.texts[key]}


@hardcore_ids
def test_coach_pushes_below_half_of_last_week(pack: MessagePack) -> None:
    for seed in range(10):
        lines = week_text(pack, 3_000, 10_000, seed).splitlines()
        assert lines[-1] in verdict_lines(pack, Key.VERDICT_PUSH, 30)


@hardcore_ids
def test_coach_acknowledges_then_raises_the_bar(pack: MessagePack) -> None:
    for seed in range(10):
        lines = week_text(pack, 12_000, 10_000, seed).splitlines()
        assert lines[-1] in verdict_lines(pack, Key.VERDICT_UP, 120)
    # Acknowledge first, then the next target: at least two sentences in every variant.
    for template in pack.texts[Key.VERDICT_UP]:
        assert len(re.findall(r"[.!]", template)) >= 2, template


@hardcore_ids
def test_coach_asks_about_injury_or_rest_after_two_empty_weeks(pack: MessagePack) -> None:
    pushes = rendered(pack, Key.VERDICT_PUSH) | rendered(pack, Key.VERDICT_STEADY)
    for seed in range(10):
        text = week_text(pack, 0, 0, seed)
        last = text.splitlines()[-1]
        assert last in rendered(pack, Key.VERDICT_ZERO_STREAK)
        assert "?" in last
        assert not any(push in text for push in pushes)


@hardcore_ids
def test_variants_are_picked_by_the_injected_rng(pack: MessagePack) -> None:
    for key in (
        Key.VERDICT_PUSH,
        Key.VERDICT_STEADY,
        Key.VERDICT_UP,
        Key.VERDICT_ZERO_STREAK,
        Key.NEW_ACTIVITY,
        Key.WEEK_NONE_YET,
    ):
        assert len(pack.texts[key]) >= 3, key
    same = {week_text(pack, 3_000, 10_000, seed=1) for _ in range(5)}
    assert len(same) == 1
    across_seeds = {week_text(pack, 3_000, 10_000, seed) for seed in range(30)}
    assert len(across_seeds) > 1


@pytest.mark.parametrize("pack", [p for p in ALL_PACKS if p.tone == "neutral"], ids=["en", "tr"])
def test_neutral_never_judges(pack: MessagePack) -> None:
    for key in (Key.VERDICT_PUSH, Key.VERDICT_STEADY, Key.VERDICT_UP, Key.VERDICT_ZERO_STREAK):
        assert pack.texts[key] == ("",)
    assert week_text(pack, 0, 0).splitlines()[-1] in {
        pack.texts[Key.WEEK_NONE][0],
        pack.texts[Key.FRESH_NEVER][0],
    }


# ---------------------------------------------------------------- blocklist


def blocked(text: str) -> list[str]:
    return BLOCKLIST_EN.findall(text) + BLOCKLIST_TR.findall(text)


@pack_ids
def test_packs_contain_no_blocked_word(pack: MessagePack) -> None:
    for key, template in every_template(pack):
        assert not blocked(template), f"{pack.tone}/{pack.lang} {key}: {blocked(template)}"


@pytest.mark.parametrize("lang", ["en", "tr"])
def test_neutral_texts_contain_no_blocked_word(lang: str) -> None:
    for key, template in NEUTRAL_TEXTS[lang].items():  # type: ignore[index]
        assert not blocked(template), f"neutral/{lang} {key}: {blocked(template)}"


# ---------------------------------------------------------------- tone-free layer (P6.8)

NUTRITION_WORDS = re.compile(
    r"\b(eat|food|kcal|calorie\w*|meal|macro\w*|protein|carb\w*|scale|sleep|energy"
    r"|yiyecek\w*|yemek\w*|öğün\w*|makro\w*|tartı\w*|uyku\w*|enerji\w*)\b",
    re.IGNORECASE,
)


@pytest.mark.parametrize("lang", ["en", "tr"])
def test_every_language_defines_every_neutral_key(lang: str) -> None:
    texts = NEUTRAL_TEXTS[lang]  # type: ignore[index]
    assert set(texts) == set(NeutralKey)
    assert set(NEUTRAL_FIELDS) == set(NeutralKey)
    for key, template in texts.items():
        used = {name for _, name, _, _ in string.Formatter().parse(template) if name}
        assert used <= NEUTRAL_FIELDS[key], f"{lang} {key}: {used - NEUTRAL_FIELDS[key]}"


@pack_ids
def test_packs_have_no_nutrition_or_body_keys(pack: MessagePack) -> None:
    """Food, the scale, sleep and energy live only in the tone-free layer."""
    key_names = {key.value for key in pack.texts}
    assert not key_names & {key.value for key in NeutralKey}
    for key in pack.texts:
        assert not re.match(r"(eat|kcal|meal|scale|weight|body|food|nutrition)", key.value), key
    if pack.tone == "hardcore":
        for key, template in every_template(pack):
            if key is Key.HELP:
                continue  # lists the command names, not wording about food
            assert not NUTRITION_WORDS.search(template), f"{pack.lang} {key}: {template}"


def test_neutral_texts_are_the_same_in_every_tone() -> None:
    for lang in ("en", "tr"):
        neutral = Messages(PACKS["neutral", lang])  # type: ignore[index]
        hardcore = Messages(PACKS["hardcore", lang])  # type: ignore[index]
        for key in NeutralKey:
            fields: dict[str, object] = dict.fromkeys(NEUTRAL_FIELDS[key], "?")
            assert neutral.neutral(key, **fields) == hardcore.neutral(key, **fields)


MILD_PROFANITY = re.compile(r"\b(damn|hell|crap|lan|ulan|hassiktir)\b", re.IGNORECASE)


@hardcore_ids
def test_rest_and_sick_answers_are_calm_in_hardcore(pack: MessagePack) -> None:
    """Rest days and being sick or injured are never pushed on (ADR 0020)."""
    for key in RESPECTFUL:
        for template in pack.texts[key]:
            assert not MILD_PROFANITY.search(template), f"{pack.lang} {key}: {template}"
            assert "!" not in template


@hardcore_ids
def test_hardcore_may_push_only_on_a_skip_without_reason(pack: MessagePack) -> None:
    neutral = PACKS["neutral", pack.lang]
    assert pack.texts[Key.CHECKIN_SKIPPED_NO_REASON] != neutral.texts[Key.CHECKIN_SKIPPED_NO_REASON]
    assert len(pack.texts[Key.CHECKIN_SKIPPED_NO_REASON]) >= 3


def test_blocklist_catches_what_it_should() -> None:
    assert blocked("Lose some weight")
    assert blocked("Şişko")
    assert blocked("Kilo vermen lazım")
    assert blocked("Sakat mısın")
    assert blocked("siktir git")
    # The allowed mild words and ordinary injury talk pass.
    assert not blocked("Hassiktir, ulan, lan. Damn, hell, crap. Sakatlık mı, dinlenme mi?")
    assert not blocked("Injured or resting?")
