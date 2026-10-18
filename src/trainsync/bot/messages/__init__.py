"""User-facing wording of the bot, notifications and assistant replies: one pack per
tone and language, chosen by `BOT_TONE` / `BOT_LANG` (ADR 0016). `formatting.py` computes the
numbers; packs only own the words around them."""

import random

from trainsync.bot.messages import hardcore_en, hardcore_tr, neutral_en, neutral_tr
from trainsync.bot.messages.keys import FIELDS, Key
from trainsync.bot.messages.pack import MessagePack, Messages
from trainsync.core.settings import BotLang, BotTone, Settings

PACKS: dict[tuple[BotTone, BotLang], MessagePack] = {
    (pack.tone, pack.lang): pack
    for pack in (neutral_en.PACK, neutral_tr.PACK, hardcore_en.PACK, hardcore_tr.PACK)
}


def messages_for(settings: Settings, rng: random.Random | None = None) -> Messages:
    return Messages(PACKS[settings.bot_tone, settings.bot_lang], rng)


__all__ = ["FIELDS", "PACKS", "Key", "MessagePack", "Messages", "messages_for"]
