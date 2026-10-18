"""What the coach says (ADR 0030): a savage line in savage mode, the tone pack's wording
otherwise. Facts (times, weights, reps) are separate lines written by the code, so a savage line
never carries a number. Both follow the chat's language (`using_lang`, ADR 0031)."""

import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from redis.asyncio import Redis

from trainsync.bot.messages import CURRENT_LANG, Key, Messages
from trainsync.coach.categories import Category
from trainsync.coach.lines import LinePack, RecentStore, RedisRecentStore, compose, load_packs
from trainsync.coach.mode import CoachMode, RedisSoftModeStore, savage_configured
from trainsync.core.settings import BotLang, Settings


@dataclass
class CoachVoice:
    msg: Messages
    mode: CoachMode
    pack: LinePack  # the default language's lines (BOT_LANG)
    recent: RecentStore
    rng: random.Random = field(default_factory=random.Random)
    # Every language's lines; the chat's language picks one (ADR 0031).
    packs: Mapping[BotLang, LinePack] = field(default_factory=dict)

    @property
    def lines(self) -> LinePack:
        lang = CURRENT_LANG.get()
        return self.packs.get(lang, self.pack) if lang is not None else self.pack

    async def savage(self) -> bool:
        return await self.mode.savage()

    async def say(self, category: Category, key: Key, facts: list[str], **fields: object) -> str:
        """Savage: the facts, then a rotated savage line (maybe with a punchline). Otherwise the
        tone pack's `key`, which carries the facts itself."""
        if await self.mode.savage():
            line = await compose(self.lines, category, self.recent, self.rng)
            return "\n".join([*facts, line])
        return self.msg(key, **fields)

    async def line(self, category: Category, key: Key, **fields: object) -> str:
        """Only the voice line, for messages that list their facts first in every mode."""
        if await self.mode.savage():
            return await compose(self.lines, category, self.recent, self.rng)
        return self.msg(key, **fields)

    async def roast(self, category: Category) -> str:
        """A savage line alone (callers check `savage()` first)."""
        return await compose(self.lines, category, self.recent, self.rng)


def build_voice(settings: Settings, redis: Redis, msg: Messages) -> CoachVoice:
    local = Path(settings.coach_messages_file) if settings.coach_messages_file else None
    packs = load_packs(local)
    return CoachVoice(
        msg=msg,
        mode=CoachMode(savage_configured(settings), RedisSoftModeStore(redis)),
        pack=packs[settings.bot_lang],
        recent=RedisRecentStore(redis),
        packs=packs,
    )
