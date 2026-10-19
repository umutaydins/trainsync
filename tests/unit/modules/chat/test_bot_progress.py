"""P8.11, ADR 0038: the progress summary in the chat, in every tone and language."""

import random
from copy import deepcopy
from datetime import date
from typing import Any

import pytest

from trainsync.core.settings import BotLang, BotProfanity, BotTone
from trainsync.modules.chat.formatting import day_range
from trainsync.modules.chat.progress import Trend, arrow, progress_message, trend
from trainsync.modules.coach.categories import Category
from trainsync.modules.coach.lines import MemoryRecentStore, load_pack
from trainsync.modules.coach.mode import CoachMode, MemorySoftModeStore
from trainsync.modules.coach.packs import PACKS, Key, Messages
from trainsync.modules.coach.savage_progress import EN_MAX, TR_LINES
from trainsync.modules.coach.voice import CoachVoice
from trainsync.modules.stats.schemas import Change
from trainsync.modules.stats.totals import StatsSummary

EXTRA: Any = StatsSummary.model_config["json_schema_extra"]
EXAMPLE: dict[str, Any] = EXTRA["examples"][0]


def summary(**changes: tuple[float, float]) -> StatsSummary:
    """The example month, with chosen (value, previous) pairs for the trend inputs."""
    data = deepcopy(EXAMPLE)
    targets = {
        "moving": data["endurance"]["totals"]["moving_time_s"],
        "tonnage": data["strength"]["tonnage_kg"],
        "days": data["consistency"]["active_days"],
    }
    for name, (value, previous) in changes.items():
        diff = value - previous
        pct = diff / previous * 100 if previous else None
        targets[name].update(value=value, previous=previous, change=diff, change_pct=pct)
    return StatsSummary.model_validate(data)


def voice(msg: Messages, lang: BotLang, profanity: BotProfanity = "roast") -> CoachVoice:
    return CoachVoice(
        msg=msg,
        mode=CoachMode(configured=True, soft=MemorySoftModeStore()),
        pack=load_pack(None, lang),
        recent=MemoryRecentStore(),
        rng=random.Random(4),
        profanity=profanity,
    )


def test_trend_from_time_tonnage_and_days() -> None:
    up = trend(summary(moving=(120, 100), tonnage=(110, 100), days=(10, 10)))
    assert up is not None
    assert (up.trend, up.percent) == (Trend.UP, 10)
    down = trend(summary(moving=(50, 100), tonnage=(80, 100), days=(8, 10)))
    assert down is not None
    assert (down.trend, down.percent) == (Trend.DOWN, 30)
    flat = trend(summary(moving=(100, 100), tonnage=(105, 100), days=(10, 10)))
    assert flat is not None
    assert flat.trend is Trend.FLAT


def test_a_drop_with_sick_days_is_recovery_and_nothing_to_compare_is_none() -> None:
    data = summary(moving=(10, 100), tonnage=(10, 100), days=(1, 10)).model_dump(by_alias=True)
    data["consistency"]["sick_days"] = 3
    sick = trend(StatsSummary.model_validate(data))
    assert sick is not None
    assert sick.trend is Trend.RECOVERY
    data["previous"] = None
    assert trend(StatsSummary.model_validate(data)) is None


def test_arrows() -> None:
    assert arrow(Change(value=12, previous=10, change=2, change_pct=20.0)) == "▲20%"
    assert arrow(Change(value=8, previous=10, change=-2, change_pct=-20.0)) == "▼20%"
    assert arrow(Change(value=10, previous=10, change=0, change_pct=0.0)) == "="
    assert arrow(Change(value=1, previous=0, change=1, change_pct=None)) == ""


@pytest.mark.parametrize("tone", ["neutral", "hardcore"])
@pytest.mark.parametrize("lang", ["en", "tr"])
async def test_the_month_in_every_tone_and_language(tone: BotTone, lang: BotLang) -> None:
    msg = Messages(PACKS[tone, lang], random.Random(1))
    month = summary()
    text = await progress_message(month, Key.PERIOD_MONTH, msg, None)
    lines = text.splitlines()
    span = day_range(date(2026, 10, 1), date(2026, 10, 19), msg)
    assert lines[0] == msg(Key.PROGRESS_TITLE, label=msg(Key.PERIOD_MONTH), range=span)
    assert any("98.4 km" in line and line.endswith("▲11%") for line in lines)
    assert any("41,250 kg" in line and line.endswith("▲9%") for line in lines)
    assert any("2480" in line and "2500" in line for line in lines)
    assert not any("80.6" in line or "81.4" in line for line in lines)  # never the scale
    up = trend(month)
    assert up is not None
    assert up.trend is Trend.UP
    verdict = msg(Key.PROGRESS_UP, percent=up.percent)
    if tone == "neutral":
        assert verdict == ""
        assert lines[-1] != ""
    else:
        assert lines[-1] == verdict


async def test_savage_praises_gains_and_roasts_drops() -> None:
    msg = Messages(PACKS["hardcore", "tr"], random.Random(1))
    gain = await progress_message(summary(), Key.PERIOD_MONTH, msg, voice(msg, "tr"))
    assert gain.splitlines()[-1] in TR_LINES[Category.PROGRESS_UP]
    en = Messages(PACKS["hardcore", "en"], random.Random(1))
    drop = summary(moving=(50, 100), tonnage=(60, 100), days=(5, 10))
    roast = await progress_message(drop, Key.DIGEST_WEEK, en, voice(en, "en", "max"))
    assert roast.splitlines()[-1] in {line for lines in EN_MAX.values() for line in lines}


async def test_recovery_is_calm_in_savage_max() -> None:
    msg = Messages(PACKS["hardcore", "en"], random.Random(1))
    data = summary(moving=(10, 100), tonnage=(10, 100), days=(1, 10)).model_dump(by_alias=True)
    data["consistency"]["sick_days"] = 2
    text = await progress_message(
        StatsSummary.model_validate(data), Key.DIGEST_WEEK, msg, voice(msg, "en", "max")
    )
    assert text.splitlines()[-1] == msg(Key.PROGRESS_RECOVERY)
    assert text.splitlines()[0].startswith("Your week")  # no max opener in front


async def test_an_empty_period() -> None:
    data = summary().model_dump(by_alias=True)
    for block in (data["endurance"]["totals"], data["strength"], data["consistency"]):
        for value in block.values():
            if isinstance(value, dict) and "value" in value:
                value.update(value=0, previous=0, change=0, change_pct=None)
    data["nutrition"]["avg_kcal"]["value"] = None
    msg = Messages(PACKS["neutral", "en"])
    text = await progress_message(StatsSummary.model_validate(data), Key.PERIOD_WEEK, msg, None)
    assert text.splitlines()[1] == msg(Key.PROGRESS_NONE)
