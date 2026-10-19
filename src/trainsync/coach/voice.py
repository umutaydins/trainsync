"""What the coach says (ADR 0030): a savage line in savage mode, the tone pack's wording
otherwise. Facts (times, weights, reps) are separate lines written by the code, so a savage line
never carries a number. Both follow the chat's language (`using_lang`, ADR 0031).

The profanity level (ADR 0032) picks the roast or the max pool of each category; in max, while
savage is in effect, `decorate` puts a `max_opener` line in front of every other message.
"""

import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from redis.asyncio import Redis

from trainsync.bot.messages import CURRENT_LANG, NEUTRAL_TEXTS, Key, Messages, NeutralKey
from trainsync.coach.categories import Category
from trainsync.coach.lines import (
    LinePack,
    RecentStore,
    RedisRecentStore,
    compose,
    load_packs,
    pick,
)
from trainsync.coach.mode import (
    CURRENT_PROFANITY,
    CoachMode,
    RedisSoftModeStore,
    savage_configured,
)
from trainsync.core.settings import BotLang, BotProfanity, Settings

# The calm replies to pain and distress (ADR 0030, 0032): a message that carries one is never
# given a max opener, whoever built it. Matched on the wording before the first field.
CALM_TEXTS = frozenset(
    texts[key].split("{", 1)[0]
    for texts in NEUTRAL_TEXTS.values()
    for key in (NeutralKey.SAFETY_PAIN, NeutralKey.SAFETY_DISTRESS)
)


@dataclass
class CoachVoice:
    msg: Messages
    mode: CoachMode
    pack: LinePack  # the default language's lines (BOT_LANG)
    recent: RecentStore
    rng: random.Random = field(default_factory=random.Random)
    # Every language's lines; the chat's language picks one (ADR 0031).
    packs: Mapping[BotLang, LinePack] = field(default_factory=dict)
    # BOT_PROFANITY; a chat's `/swear` choice overrides it (`using_profanity`, ADR 0032).
    profanity: BotProfanity = "roast"

    @property
    def lines(self) -> LinePack:
        lang = CURRENT_LANG.get()
        return self.packs.get(lang, self.pack) if lang is not None else self.pack

    @property
    def level(self) -> BotProfanity:
        """The chat's profanity level, else `BOT_PROFANITY`."""
        return CURRENT_PROFANITY.get() or self.profanity

    async def savage(self) -> bool:
        return await self.mode.savage()

    async def swears_everywhere(self) -> bool:
        """Max profanity in effect: savage (configured, not soft) and the level is `max`."""
        return self.level == "max" and await self.mode.savage()

    async def say(self, category: Category, key: Key, facts: list[str], **fields: object) -> str:
        """Savage: the facts, then a rotated savage line (maybe with a punchline). Otherwise the
        tone pack's `key`, which carries the facts itself."""
        if await self.mode.savage():
            line = await compose(self.lines, category, self.recent, self.rng, self.level)
            return "\n".join([*facts, line])
        return self.msg(key, **fields)

    async def line(self, category: Category, key: Key, **fields: object) -> str:
        """Only the voice line, for messages that list their facts first in every mode."""
        if await self.mode.savage():
            return await compose(self.lines, category, self.recent, self.rng, self.level)
        return self.msg(key, **fields)

    async def roast(self, category: Category) -> str:
        """A savage line alone (callers check `savage()` first)."""
        return await compose(self.lines, category, self.recent, self.rng, self.level)

    async def decorate(self, text: str) -> str:
        """In max profanity, every message swears: a rotated `max_opener` line in front of a
        message that carries no savage line yet. Otherwise `text` unchanged. Calm replies (pain,
        distress) must never come through here."""
        if not text or any(calm in text for calm in CALM_TEXTS):
            return text
        if not await self.swears_everywhere():
            return text
        packs = [self.pack, *self.packs.values()]
        if any(line in text for pack in packs for pool in pack.max.values() for line in pool):
            return text  # already a max line in it (any language): never two
        opener = await pick(self.lines, Category.MAX_OPENER, self.recent, self.rng, "max")
        return f"{opener}\n{text}"


def build_voice(settings: Settings, redis: Redis, msg: Messages) -> CoachVoice:
    local = Path(settings.coach_messages_file) if settings.coach_messages_file else None
    packs = load_packs(local)
    return CoachVoice(
        msg=msg,
        mode=CoachMode(savage_configured(settings), RedisSoftModeStore(redis)),
        pack=packs[settings.bot_lang],
        recent=RedisRecentStore(redis),
        packs=packs,
        profanity=settings.bot_profanity,
    )
