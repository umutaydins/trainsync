"""`MessagePack` (the wording of one tone and language) and `Messages` (a pack plus the RNG that
picks among a key's variants).

The language can change per chat at runtime (`/lang`, ADR 0031): `using_lang()` sets it for the
current task (the bot per update, the worker per send), and a `Messages` built with `languages`
renders in that language; without one set, it uses its default pack (`BOT_LANG`).
"""

import random
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime

from trainsync.bot.messages.keys import Key
from trainsync.bot.messages.neutral import NEUTRAL_TEXTS, NeutralKey
from trainsync.core.settings import BotLang, BotTone


@dataclass(frozen=True, slots=True)
class MessagePack:
    tone: BotTone
    lang: BotLang
    texts: Mapping[Key, tuple[str, ...]]
    months: tuple[str, ...]  # short names, January first
    weekdays: tuple[str, ...]  # short names, Monday first


CURRENT_LANG: ContextVar[BotLang | None] = ContextVar("trainsync_lang", default=None)


@contextmanager
def using_lang(lang: BotLang | None) -> Iterator[None]:
    """Render in `lang` inside this block (None: each `Messages` falls back to its default)."""
    token = CURRENT_LANG.set(lang)
    try:
        yield
    finally:
        CURRENT_LANG.reset(token)


class Messages:
    """`msg(Key.X, field=...)` renders one variant of a key. A key with several variants is
    picked with the injected RNG, so a seeded `random.Random` makes replies deterministic.
    With `languages`, the pack follows the language set by `using_lang()`."""

    def __init__(
        self,
        pack: MessagePack,
        rng: random.Random | None = None,
        *,
        languages: Mapping[BotLang, MessagePack] | None = None,
    ) -> None:
        self._default = pack
        self._languages: Mapping[BotLang, MessagePack] = languages or {}
        self._rng = rng or random.Random()  # noqa: S311  (wording, not crypto)

    @property
    def pack(self) -> MessagePack:
        lang = CURRENT_LANG.get()
        if lang is None:
            return self._default
        return self._languages.get(lang, self._default)

    @property
    def tone(self) -> BotTone:
        return self.pack.tone

    @property
    def lang(self) -> BotLang:
        return self.pack.lang

    def __call__(self, key: Key, **fields: object) -> str:
        variants = self.pack.texts[key]
        template = variants[0] if len(variants) == 1 else self._rng.choice(variants)
        return template.format(**fields)

    def neutral(self, key: NeutralKey, **fields: object) -> str:
        """Tone-free wording (nutrition, scale, sleep, energy): the same in every tone."""
        return NEUTRAL_TEXTS[self.pack.lang][key].format(**fields)

    def help(self) -> str:
        """The tone's help plus the tone-free nutrition lines. Command names and their
        descriptions stay English in every chat language (ADR 0031)."""
        pack = self._languages.get("en", self.pack)
        nutrition = NEUTRAL_TEXTS[pack.lang][NeutralKey.HELP_NUTRITION].format(
            scale_command="/weight"
        )
        return f"{pack.texts[Key.HELP][0]}\n{nutrition}"

    def day(self, day: date) -> str:
        """`14 Oct`"""
        return f"{day.day} {self.pack.months[day.month - 1]}"

    def day_time(self, moment: datetime) -> str:
        """`10 Oct 08:00`"""
        return f"{self.day(moment)} {moment:%H:%M}"

    def weekday_time(self, moment: datetime) -> str:
        """`Wed 14 Oct 06:30`"""
        return f"{self.pack.weekdays[moment.weekday()]} {self.day_time(moment)}"
