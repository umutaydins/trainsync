"""User-facing wording of the bot, notifications and assistant replies: one pack per
tone and language, chosen by `BOT_TONE` / `BOT_LANG` (ADR 0016). `formatting.py` computes the
numbers; packs only own the words around them."""

import random

from trainsync.bot.messages import hardcore_en, hardcore_tr, neutral_en, neutral_tr
from trainsync.bot.messages.keys import FIELDS, RESPECTFUL, Key
from trainsync.bot.messages.neutral import NEUTRAL_FIELDS, NEUTRAL_TEXTS, NeutralKey
from trainsync.bot.messages.pack import CURRENT_LANG, MessagePack, Messages, using_lang
from trainsync.core.settings import BotLang, BotTone, Settings

PACKS: dict[tuple[BotTone, BotLang], MessagePack] = {
    (pack.tone, pack.lang): pack
    for pack in (neutral_en.PACK, neutral_tr.PACK, hardcore_en.PACK, hardcore_tr.PACK)
}


LANGUAGES: tuple[BotLang, ...] = ("en", "tr")


def messages_for(settings: Settings, rng: random.Random | None = None) -> Messages:
    """`BOT_TONE` in every language; `BOT_LANG` unless a chat chose another (ADR 0031)."""
    return Messages(
        PACKS[settings.bot_tone, settings.bot_lang],
        rng,
        languages={lang: PACKS[settings.bot_tone, lang] for lang in LANGUAGES},
    )


__all__ = [
    "CURRENT_LANG",
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
]
