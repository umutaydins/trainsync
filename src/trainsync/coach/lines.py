"""Savage lines: the built-in pack plus the owner's local file, rotation and punchlines.

- `load_pack` merges `config/messages.local.yaml` (optional, git-ignored; same categories as
  `savage_tr.LINES`) into the built-in lines. Local lines are sent verbatim; a line that breaks a
  guardrail (`guardrails.violations`) is dropped with a log line, never edited.
- `pick` chooses a line at random among those not sent in the last `RECENT` sends of that
  category; with fewer lines than that, the least recently sent one. The history lives in Redis,
  so the bot and the worker rotate together and a restart forgets nothing.
- `compose` is one savage message: a line, and about 1 in 4 times a `punchline_en` line after it.
"""

import hashlib
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import yaml
from redis.asyncio import Redis

from trainsync.coach.categories import Category
from trainsync.coach.guardrails import Violation, violations
from trainsync.coach.savage_tr import LINES
from trainsync.core.logging import get_logger

log = get_logger(__name__)

RECENT = 10
PUNCHLINE_CHANCE = 0.25


@dataclass(frozen=True, slots=True)
class DroppedLine:
    category: str
    text: str
    reasons: tuple[Violation, ...]


@dataclass(frozen=True, slots=True)
class LinePack:
    lines: Mapping[Category, tuple[str, ...]]
    dropped: tuple[DroppedLine, ...] = ()
    local_count: int = 0


def read_local(path: Path) -> dict[str, list[str]]:
    """`{category: [line, ...]}` from the local YAML file; empty when it does not exist.
    Anything that is not a list of strings under a known category is ignored (and logged)."""
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        log.warning("coach_local_lines_unreadable", path=str(path), error=str(exc))
        return {}
    if not isinstance(data, dict):
        return {}
    known = {c.value for c in Category}
    result: dict[str, list[str]] = {}
    for key, value in data.items():
        if str(key) not in known:
            log.warning("coach_local_lines_unknown_category", category=str(key))
            continue
        if not isinstance(value, list):
            continue
        result[str(key)] = [
            item.strip() for item in value if isinstance(item, str) and item.strip()
        ]
    return result


def merge(base: Mapping[Category, tuple[str, ...]], local: Mapping[str, list[str]]) -> LinePack:
    lines = {category: list(texts) for category, texts in base.items()}
    dropped: list[DroppedLine] = []
    added = 0
    for name, texts in local.items():
        category = Category(name)
        for text in texts:
            reasons = violations(text)
            if reasons:
                dropped.append(DroppedLine(name, text, tuple(reasons)))
                continue
            if text not in lines[category]:
                lines[category].append(text)
                added += 1
    for line in dropped:
        log.warning(
            "coach_local_line_dropped",
            category=line.category,
            reasons=[r.value for r in line.reasons],
        )
    return LinePack({c: tuple(t) for c, t in lines.items()}, tuple(dropped), added)


def load_pack(local_file: Path | None) -> LinePack:
    """The built-in savage lines with the owner's local lines merged in."""
    return merge(LINES, read_local(local_file) if local_file else {})


def line_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class RecentStore(Protocol):
    """Ids of the lines last sent per category, newest first."""

    async def recent(self, category: Category) -> list[str]: ...

    async def remember(self, category: Category, line: str) -> None: ...


class RedisRecentStore:
    def __init__(self, redis: Redis, keep: int = RECENT) -> None:
        self._redis = redis
        self._keep = keep

    @staticmethod
    def _key(category: Category) -> str:
        return f"coach:recent:{category.value}"

    async def recent(self, category: Category) -> list[str]:
        raw = await self._redis.lrange(self._key(category), 0, self._keep - 1)  # type: ignore[misc]
        return [item.decode() if isinstance(item, bytes) else str(item) for item in raw]

    async def remember(self, category: Category, line: str) -> None:
        key = self._key(category)
        await self._redis.lpush(key, line_id(line))  # type: ignore[misc]
        await self._redis.ltrim(key, 0, self._keep - 1)  # type: ignore[misc]


@dataclass
class MemoryRecentStore:
    """For tests and for a process without Redis."""

    keep: int = RECENT
    history: dict[Category, list[str]] = field(default_factory=dict)

    async def recent(self, category: Category) -> list[str]:
        return self.history.get(category, [])[: self.keep]

    async def remember(self, category: Category, line: str) -> None:
        self.history[category] = [line_id(line), *self.history.get(category, [])][: self.keep]


async def pick(pack: LinePack, category: Category, store: RecentStore, rng: random.Random) -> str:
    lines = pack.lines[category]
    recent = await store.recent(category)
    fresh = [line for line in lines if line_id(line) not in recent]
    if fresh:
        choice = rng.choice(fresh)
    else:
        # Fewer lines than the history: the one sent longest ago.
        position: dict[str, int] = {}
        for index, sent in enumerate(recent):  # newest first: keep each line's latest send
            position.setdefault(sent, index)
        choice = max(lines, key=lambda line: position.get(line_id(line), -1))
    await store.remember(category, choice)
    return choice


async def compose(
    pack: LinePack, category: Category, store: RecentStore, rng: random.Random
) -> str:
    """A savage message of `category`, with an English punchline about 1 in 4 times."""
    text = await pick(pack, category, store, rng)
    if rng.random() < PUNCHLINE_CHANCE:
        text = f"{text} {await pick(pack, Category.PUNCHLINE_EN, store, rng)}"
    return text
