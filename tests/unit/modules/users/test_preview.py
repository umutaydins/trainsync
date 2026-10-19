"""P8.13: the onboarding's coach preview uses the bot's own wording."""

import random

from trainsync.modules.coach.packs import PACKS
from trainsync.modules.coach.savage_en import MAX
from trainsync.modules.coach.savage_tr import LINES
from trainsync.modules.users.preview import PREVIEW_CATEGORY, PREVIEW_KEY, preview


def test_the_tone_pack_line_unless_savage() -> None:
    sample = preview("neutral", "savage", "max", "tr", random.Random(1))
    assert not sample.savage  # savage belongs to the hardcore tone (ADR 0031)
    assert sample.line in PACKS["neutral", "tr"].texts[PREVIEW_KEY]
    hardcore = preview("hardcore", "normal", "roast", "en", random.Random(1))
    assert hardcore.line in PACKS["hardcore", "en"].texts[PREVIEW_KEY]


def test_savage_lines_follow_the_profanity_level() -> None:
    roast = preview("hardcore", "savage", "roast", "tr", random.Random(2))
    assert roast.savage
    assert roast.line in LINES[PREVIEW_CATEGORY]
    maxed = preview("hardcore", "savage", "max", "en", random.Random(2))
    assert maxed.line in MAX[PREVIEW_CATEGORY]
