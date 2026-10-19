"""User-facing wording of the bot, notifications and assistant replies: one pack per
tone and language, chosen by `BOT_TONE` / `BOT_LANG` (ADR 0016). `formatting.py` computes the
numbers; packs only own the words around them."""

import random

from trainsync.core.settings import BotLang, BotTone, Settings
from trainsync.modules.coach.packs import hardcore_en, hardcore_tr, neutral_en, neutral_tr
from trainsync.modules.coach.packs.keys import FIELDS, RESPECTFUL, Key
from trainsync.modules.coach.packs.neutral import NEUTRAL_FIELDS, NEUTRAL_TEXTS, NeutralKey
from trainsync.modules.coach.packs.pack import (
    CURRENT_EMERGENCY,
    CURRENT_LANG,
    CURRENT_TONE,
    MessagePack,
    Messages,
    using_lang,
    using_tone,
)

PACKS: dict[tuple[BotTone, BotLang], MessagePack] = {
    (pack.tone, pack.lang): pack
    for pack in (neutral_en.PACK, neutral_tr.PACK, hardcore_en.PACK, hardcore_tr.PACK)
}


LANGUAGES: tuple[BotLang, ...] = ("en", "tr")


def messages_for(settings: Settings, rng: random.Random | None = None) -> Messages:
    """Every tone and language; `BOT_TONE` and `BOT_LANG` unless the user chose (ADR 0036)."""
    return Messages(
        PACKS[settings.bot_tone, settings.bot_lang],
        rng,
        packs=PACKS,
        emergency_number=settings.emergency_number,
    )


__all__ = [
    "CURRENT_EMERGENCY",
    "CURRENT_LANG",
    "CURRENT_TONE",
    "FIELDS",
    "LANGUAGES",
    "NEUTRAL_FIELDS",
    "NEUTRAL_TEXTS",
    "PACKS",
    "RESPECTFUL",
    "Key",
    "MessagePack",
    "Messages",
    "NeutralKey",
    "messages_for",
    "using_lang",
    "using_tone",
]
