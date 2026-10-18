"""`MessagePack` (the wording of one tone and language) and `Messages` (a pack plus the RNG that
picks among a key's variants)."""

import random
from collections.abc import Mapping
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


class Messages:
    """`msg(Key.X, field=...)` renders one variant of a key. A key with several variants is
    picked with the injected RNG, so a seeded `random.Random` makes replies deterministic."""

    def __init__(self, pack: MessagePack, rng: random.Random | None = None) -> None:
        self.pack = pack
        self._rng = rng or random.Random()  # noqa: S311  (wording, not crypto)

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
        """The pack's help plus the tone-free nutrition lines."""
        nutrition = self.neutral(NeutralKey.HELP_NUTRITION, scale_command="/weight")
        return f"{self(Key.HELP)}\n{nutrition}"

    def day(self, day: date) -> str:
        """`14 Oct`"""
        return f"{day.day} {self.pack.months[day.month - 1]}"

    def day_time(self, moment: datetime) -> str:
        """`10 Oct 08:00`"""
        return f"{self.day(moment)} {moment:%H:%M}"

    def weekday_time(self, moment: datetime) -> str:
        """`Wed 14 Oct 06:30`"""
        return f"{self.pack.weekdays[moment.weekday()]} {self.day_time(moment)}"
