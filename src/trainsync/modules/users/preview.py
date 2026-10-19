"""A sample of how the coach would sound with given settings (onboarding, P8.13).

The same wording the bot and the worker use: the tone pack's "workout done" line, or a savage
line (roast or max pool) for savage with the hardcore tone (ADR 0030, 0031, 0032).
"""

import random
from dataclasses import dataclass
from functools import cache

from trainsync.core.settings import BotIntensity, BotLang, BotProfanity, BotTone
from trainsync.modules.coach.categories import Category
from trainsync.modules.coach.lines import LinePack, load_packs
from trainsync.modules.coach.packs import PACKS, Key

# A finished workout: the friendliest moment to hear the coach for the first time.
PREVIEW_KEY = Key.COACH_DONE_GOOD
PREVIEW_CATEGORY = Category.WORKOUT_DONE_GOOD


@dataclass(frozen=True, slots=True)
class Preview:
    line: str
    savage: bool


@cache
def _savage_packs() -> dict[BotLang, LinePack]:
    """The built-in savage lines (the owner's local file is the bot's, not a preview's)."""
    return load_packs(None)


def preview(
    tone: BotTone,
    intensity: BotIntensity,
    profanity: BotProfanity,
    lang: BotLang,
    rng: random.Random | None = None,
) -> Preview:
    chooser = rng or random.Random()  # noqa: S311  (variety, not security)
    savage = intensity == "savage" and tone == "hardcore"
    if savage:
        pool = _savage_packs()[lang].pool(PREVIEW_CATEGORY, profanity)
    else:
        pool = PACKS[tone, lang].texts[PREVIEW_KEY]
    return Preview(chooser.choice(pool), savage)
