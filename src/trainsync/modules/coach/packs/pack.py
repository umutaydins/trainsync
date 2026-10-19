"""`MessagePack` (the wording of one tone and language) and `Messages` (a pack plus the RNG that
picks among a key's variants).

The language and the tone are each user's (`/lang`, ADR 0031, 0036): `using_lang()` and
`using_tone()` set them for the current task (the bot per update, the worker per send), and a
`Messages` built with `packs` renders in that tone and language; without them set, it uses its
default pack (`BOT_TONE`, `BOT_LANG`).
"""

import random
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime

from trainsync.core.settings import DEFAULT_EMERGENCY_NUMBER, BotLang, BotTone
from trainsync.modules.coach.packs.keys import Key
from trainsync.modules.coach.packs.neutral import NEUTRAL_TEXTS, NeutralKey


@dataclass(frozen=True, slots=True)
class MessagePack:
    tone: BotTone
    lang: BotLang
    texts: Mapping[Key, tuple[str, ...]]
    months: tuple[str, ...]  # short names, January first
    weekdays: tuple[str, ...]  # short names, Monday first


CURRENT_LANG: ContextVar[BotLang | None] = ContextVar("trainsync_lang", default=None)
CURRENT_TONE: ContextVar[BotTone | None] = ContextVar("trainsync_tone", default=None)
# The user's emergency number (from their country, ADR 0036) for the distress reply.
CURRENT_EMERGENCY: ContextVar[str | None] = ContextVar("trainsync_emergency", default=None)


@contextmanager
def using_lang(lang: BotLang | None) -> Iterator[None]:
    """Render in `lang` inside this block (None: each `Messages` falls back to its default)."""
    token = CURRENT_LANG.set(lang)
    try:
        yield
    finally:
        CURRENT_LANG.reset(token)


@contextmanager
def using_tone(tone: BotTone | None) -> Iterator[None]:
    """Render in `tone` inside this block (None: the default tone)."""
    token = CURRENT_TONE.set(tone)
    try:
        yield
    finally:
        CURRENT_TONE.reset(token)


class Messages:
    """`msg(Key.X, field=...)` renders one variant of a key. A key with several variants is
    picked with the injected RNG, so a seeded `random.Random` makes replies deterministic.
    With `languages` (the default tone in each language) or `packs` (every tone and language),
    the pack follows `using_lang()` and `using_tone()`."""

    def __init__(
        self,
        pack: MessagePack,
        rng: random.Random | None = None,
        *,
        languages: Mapping[BotLang, MessagePack] | None = None,
        packs: Mapping[tuple[BotTone, BotLang], MessagePack] | None = None,
        emergency_number: str = DEFAULT_EMERGENCY_NUMBER,
    ) -> None:
        self._default = pack
        self._emergency = emergency_number
        self._packs: dict[tuple[BotTone, BotLang], MessagePack] = dict(packs or {})
        for lang, by_lang in (languages or {}).items():
            self._packs.setdefault((pack.tone, lang), by_lang)
        self._rng = rng or random.Random()  # noqa: S311  (wording, not crypto)

    @property
    def pack(self) -> MessagePack:
        tone = CURRENT_TONE.get() or self._default.tone
        lang = CURRENT_LANG.get() or self._default.lang
        return self._packs.get(
            (tone, lang), self._packs.get((self._default.tone, lang), self._default)
        )

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
        context = {"emergency": CURRENT_EMERGENCY.get() or self._emergency}
        return NEUTRAL_TEXTS[self.pack.lang][key].format(**{**context, **fields})

    def help(self) -> str:
        """The tone's help plus the tone-free nutrition lines. Command names and their
        descriptions stay English in every chat language (ADR 0031)."""
        tone = CURRENT_TONE.get() or self._default.tone
        pack = self._packs.get((tone, "en"), self.pack)
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
