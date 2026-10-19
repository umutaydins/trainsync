"""Savage lines: the built-in packs (one per language, each with a roast and a max pool) plus
the owner's local file, rotation and punchlines.

- `load_packs` merges `config/messages.local.yaml` (optional, git-ignored) into the built-in
  lines of each language. The file has a `tr:` and an `en:` section with the categories of
  `savage_tr.LINES` / `savage_en.LINES`, and a top-level `punchline_en` list that goes into both
  (ADR 0031); categories at the top level (the first format) count as Turkish. Each language
  section may hold a `max:` section with the same categories plus `max_opener` (the max
  profanity pool, ADR 0032), and a top-level `punchline_en_max` goes into both max pools. Local
  lines are sent verbatim; a line that breaks a guardrail (`guardrails.violations`) is dropped
  with a log line, never edited.
- `pick` chooses a line at random among those not sent in the last `RECENT` sends of that
  category; with fewer lines than that, the least recently sent one. The history lives in Redis,
  so the bot and the worker rotate together and a restart forgets nothing.
- `compose` is one savage message: a line, and about 1 in 4 times a `punchline_en` line after it,
  both from the max pool when the profanity level is `max`.
"""

import hashlib
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import yaml
from redis.asyncio import Redis

from trainsync.core.logging import get_logger
from trainsync.core.settings import BotLang, BotProfanity
from trainsync.modules.coach import savage_en, savage_tr
from trainsync.modules.coach.categories import Category
from trainsync.modules.coach.guardrails import Violation, violations

log = get_logger(__name__)

RECENT = 10
PUNCHLINE_CHANCE = 0.25
Lines = Mapping[Category, tuple[str, ...]]
SAVAGE: Mapping[BotLang, Lines] = {
    "tr": savage_tr.LINES,
    "en": savage_en.LINES,
}
SAVAGE_MAX: Mapping[BotLang, Lines] = {
    "tr": savage_tr.MAX,
    "en": savage_en.MAX,
}
MAX_SECTION = "max"
PUNCHLINE_MAX = "punchline_en_max"
LocalLines = dict[str, list[str]]  # {category: [line, ...]}


@dataclass(frozen=True, slots=True)
class DroppedLine:
    category: str
    text: str
    reasons: tuple[Violation, ...]


@dataclass(frozen=True, slots=True)
class LinePack:
    lines: Lines  # roast pool
    dropped: tuple[DroppedLine, ...] = ()
    local_count: int = 0
    max: Lines = field(default_factory=dict)  # max profanity pool (ADR 0032)

    def pool(self, category: Category, profanity: BotProfanity = "roast") -> tuple[str, ...]:
        """The lines of `category` at this profanity level (roast when max has none)."""
        if profanity == "max" and self.max.get(category):
            return self.max[category]
        return self.lines[category]


@dataclass(frozen=True, slots=True)
class LocalPack:
    roast: dict[BotLang, LocalLines] = field(default_factory=dict)
    max: dict[BotLang, LocalLines] = field(default_factory=dict)


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


def _add(lines: LocalLines, category: Category, texts: list[str]) -> None:
    if texts:
        lines[category.value] = [*lines.get(category.value, []), *texts]


def read_local_pack(path: Path) -> LocalPack:
    """Roast and max lines per language from the local YAML file; empty when it does not
    exist."""
    if not path.is_file():
        return LocalPack()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        log.warning("coach_local_lines_unreadable", path=str(path), error=str(exc))
        return LocalPack()
    if not isinstance(data, dict):
        return LocalPack()
    sections = {lang: data.pop(lang, None) for lang in SAVAGE}
    max_punchlines = data.pop(PUNCHLINE_MAX, None)
    top = _categories(data)
    punchlines = top.pop(Category.PUNCHLINE_EN.value, [])
    shared_max = (
        [t.strip() for t in max_punchlines if isinstance(t, str) and t.strip()]
        if isinstance(max_punchlines, list)
        else []
    )
    result = LocalPack()
    for lang, section in sections.items():
        section = dict(section) if isinstance(section, dict) else {}
        max_section = section.pop(MAX_SECTION, None)
        lines = _categories(section)
        if lang == "tr":
            for category, texts in top.items():
                lines[category] = [*lines.get(category, []), *texts]
        _add(lines, Category.PUNCHLINE_EN, punchlines)
        max_lines = _categories(max_section) if isinstance(max_section, dict) else {}
        _add(max_lines, Category.PUNCHLINE_EN, shared_max)
        if lines:
            result.roast[lang] = lines
        if max_lines:
            result.max[lang] = max_lines
    return result


def read_local(path: Path) -> dict[BotLang, LocalLines]:
    """`{lang: {category: [line, ...]}}` (roast lines) from the local YAML file; empty when it
    does not exist. The top-level `punchline_en` goes into every language; other top-level
    categories (the format before the language sections) count as Turkish."""
    return read_local_pack(path).roast


def _merge_lines(
    base: Lines, local: Mapping[str, list[str]], pool: str
) -> tuple[dict[Category, tuple[str, ...]], list[DroppedLine], int]:
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
            known = lines.setdefault(category, [])
            if text not in known:
                known.append(text)
                added += 1
    for line in dropped:
        log.warning(
            "coach_local_line_dropped",
            category=line.category,
            pool=pool,
            reasons=[r.value for r in line.reasons],
        )
    return {c: tuple(t) for c, t in lines.items()}, dropped, added


def merge(
    base: Lines,
    local: Mapping[str, list[str]],
    max_base: Lines | None = None,
    max_local: Mapping[str, list[str]] | None = None,
) -> LinePack:
    """One language's built-in lines plus its local lines (guardrail breakers dropped), for the
    roast pool and the max pool."""
    lines, dropped, added = _merge_lines(base, local, "roast")
    max_lines, max_dropped, max_added = _merge_lines(max_base or {}, max_local or {}, "max")
    return LinePack(lines, (*dropped, *max_dropped), added + max_added, max_lines)


def load_packs(local_file: Path | None) -> dict[BotLang, LinePack]:
    """The built-in savage lines of every language with the owner's local lines merged in."""
    local = read_local_pack(local_file) if local_file else LocalPack()
    return {
        lang: merge(lines, local.roast.get(lang, {}), SAVAGE_MAX[lang], local.max.get(lang, {}))
        for lang, lines in SAVAGE.items()
    }


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


async def pick(
    pack: LinePack,
    category: Category,
    store: RecentStore,
    rng: random.Random,
    profanity: BotProfanity = "roast",
) -> str:
    lines = pack.pool(category, profanity)
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
    pack: LinePack,
    category: Category,
    store: RecentStore,
    rng: random.Random,
    profanity: BotProfanity = "roast",
) -> str:
    """A savage message of `category`, with an English punchline about 1 in 4 times."""
    text = await pick(pack, category, store, rng, profanity)
    if rng.random() < PUNCHLINE_CHANCE:
        punchline = await pick(pack, Category.PUNCHLINE_EN, store, rng, profanity)
        text = f"{text} {punchline}"
    return text
