"""Savage lines: the built-in packs (one per language) plus the owner's local file, rotation and
punchlines.

- `load_packs` merges `config/messages.local.yaml` (optional, git-ignored) into the built-in
  lines of each language. The file has a `tr:` and an `en:` section with the categories of
  `savage_tr.LINES` / `savage_en.LINES`, and a top-level `punchline_en` list that goes into both
  (ADR 0031); categories at the top level (the first format) count as Turkish. Local lines are
  sent verbatim; a line that breaks a guardrail (`guardrails.violations`) is dropped with a log
  line, never edited.
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

from trainsync.coach import savage_en, savage_tr
from trainsync.coach.categories import Category
from trainsync.coach.guardrails import Violation, violations
from trainsync.core.logging import get_logger
from trainsync.core.settings import BotLang

log = get_logger(__name__)

RECENT = 10
PUNCHLINE_CHANCE = 0.25
SAVAGE: Mapping[BotLang, Mapping[Category, tuple[str, ...]]] = {
    "tr": savage_tr.LINES,
    "en": savage_en.LINES,
}
LocalLines = dict[str, list[str]]  # {category: [line, ...]}


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


def _categories(data: Mapping[object, object]) -> LocalLines:
    """The known categories of one section. Anything that is not a list of strings under a known
    category is ignored (and logged)."""
    known = {c.value for c in Category}
    result: LocalLines = {}
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


def read_local(path: Path) -> dict[BotLang, LocalLines]:
    """`{lang: {category: [line, ...]}}` from the local YAML file; empty when it does not exist.
    The top-level `punchline_en` goes into every language; other top-level categories (the
    format before the language sections) count as Turkish."""
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        log.warning("coach_local_lines_unreadable", path=str(path), error=str(exc))
        return {}
    if not isinstance(data, dict):
        return {}
    sections = {lang: data.pop(lang, None) for lang in SAVAGE}
    top = _categories(data)
    punchlines = top.pop(Category.PUNCHLINE_EN.value, [])
    result: dict[BotLang, LocalLines] = {}
    for lang, section in sections.items():
        lines = _categories(section) if isinstance(section, dict) else {}
        if lang == "tr":
            for category, texts in top.items():
                lines[category] = [*lines.get(category, []), *texts]
        if punchlines:
            own = lines.get(Category.PUNCHLINE_EN.value, [])
            lines[Category.PUNCHLINE_EN.value] = [*own, *punchlines]
        if lines:
            result[lang] = lines
    return result


def merge(base: Mapping[Category, tuple[str, ...]], local: Mapping[str, list[str]]) -> LinePack:
    """One language's built-in lines plus its local lines (guardrail breakers dropped)."""
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


def load_packs(local_file: Path | None) -> dict[BotLang, LinePack]:
    """The built-in savage lines of every language with the owner's local lines merged in."""
    local = read_local(local_file) if local_file else {}
    return {lang: merge(lines, local.get(lang, {})) for lang, lines in SAVAGE.items()}


def load_pack(local_file: Path | None, lang: BotLang = "tr") -> LinePack:
    return load_packs(local_file)[lang]


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
