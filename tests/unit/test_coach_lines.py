"""P6.11: the savage pack, the local override file, rotation and punchlines (ADR 0030)."""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

import random
import re
from collections import Counter
from pathlib import Path

import pytest

from trainsync.coach.categories import MESSAGE_CATEGORIES, Category
from trainsync.coach.guardrails import violations
from trainsync.coach.lines import (
    RECENT,
    LinePack,
    MemoryRecentStore,
    compose,
    line_id,
    load_pack,
    merge,
    pick,
    read_local,
)
from trainsync.coach.savage_tr import LINES

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "config" / "messages.local.example.yaml"
# A few names a "quote a famous coach/athlete" line would carry: none may appear.
REAL_PEOPLE = re.compile(r"goggins|rocky|schwarzenegger|arnold|bruce lee|kobe|jordan|ali\b", re.I)


def test_pack_size_and_categories() -> None:
    assert set(LINES) == set(Category)
    assert sum(len(LINES[c]) for c in MESSAGE_CATEGORIES) >= 60
    assert len(LINES[Category.PUNCHLINE_EN]) >= 20
    assert all(len(LINES[c]) >= 5 for c in MESSAGE_CATEGORIES)
    for lines in LINES.values():
        assert len(lines) == len(set(lines)), "duplicate line"


@pytest.mark.parametrize("category", list(Category))
def test_built_in_lines_respect_the_guardrails(category: Category) -> None:
    for line in LINES[category]:
        assert violations(line) == [], line
        assert not REAL_PEOPLE.search(line), line
        assert not re.search(r"\d+\s*(?:kg|kcal|kalori|calorie)", line, re.I), line


def test_savage_lines_do_swear() -> None:
    """The owner asked for it; the pack must not be quietly mild."""
    text = " ".join(line for c in MESSAGE_CATEGORIES for line in LINES[c]).lower()
    for word in ("amına koyayım", "siktir", "amk", "hassiktir", "ulan"):
        assert word in text, word


def test_punchlines_are_short_english() -> None:
    for line in LINES[Category.PUNCHLINE_EN]:
        assert len(line) <= 45, line
        assert line.isascii(), line


def test_example_local_file_covers_every_category_and_is_clean() -> None:
    local = read_local(EXAMPLE)
    assert set(local) == {c.value for c in Category}
    pack = merge(LINES, local)
    assert pack.dropped == ()
    assert pack.local_count == sum(len(v) for v in local.values()) - 1  # one duplicates a built-in


def test_local_lines_are_merged_verbatim_and_bad_ones_dropped(tmp_path: Path) -> None:
    path = tmp_path / "messages.local.yaml"
    path.write_text(
        "excuse:\n"
        '  - "  Kalk lan, amına koyayım, bahaneni sonra anlatırsın.  "\n'
        '  - "Şişko gibi oturma."\n'  # body shaming: dropped
        "  - 42\n"  # not text: ignored
        "unknown_category:\n"
        '  - "ignored"\n'
        "punchline_en:\n"
        '  - "Lift first. Talk later."\n'
        '  - "Burn it off tomorrow."\n',  # calorie punishment: dropped
        encoding="utf-8",
    )
    pack = load_pack(path)
    assert "Kalk lan, amına koyayım, bahaneni sonra anlatırsın." in pack.lines[Category.EXCUSE]
    assert "Lift first. Talk later." in pack.lines[Category.PUNCHLINE_EN]
    assert pack.local_count == 2
    assert [d.text for d in pack.dropped] == ["Şişko gibi oturma.", "Burn it off tomorrow."]
    assert all(line not in pack.lines[Category.EXCUSE] for line in ("Şişko gibi oturma.",))


def test_missing_or_broken_local_file_is_just_the_built_in_pack(tmp_path: Path) -> None:
    assert load_pack(tmp_path / "absent.yaml").lines == load_pack(None).lines
    broken = tmp_path / "broken.yaml"
    broken.write_text("excuse: [unclosed", encoding="utf-8")
    assert read_local(broken) == {}


async def test_rotation_never_repeats_the_last_ten() -> None:
    lines = tuple(f"line {n}" for n in range(14))
    pack = LinePack({**LINES, Category.EXCUSE: lines})
    store = MemoryRecentStore()
    rng = random.Random(3)
    sent = [await pick(pack, Category.EXCUSE, store, rng) for _ in range(300)]
    for index, line in enumerate(sent):
        assert line not in sent[max(0, index - RECENT) : index], index


async def test_rotation_with_fewer_lines_takes_the_least_recent() -> None:
    lines = ("a", "b", "c", "d")
    pack = LinePack({**LINES, Category.REST_OVER: lines})
    store = MemoryRecentStore()
    sent = [await pick(pack, Category.REST_OVER, store, random.Random(1)) for _ in range(12)]
    # Every window of 4 holds each line once: nothing repeats before all others were used.
    for start in range(0, 12, 4):
        assert sorted(sent[start : start + 4]) == list(lines)


async def test_rotation_is_shared_through_the_store() -> None:
    store = MemoryRecentStore()
    pack = load_pack(None)
    first = await pick(pack, Category.REST_OVER, store, random.Random(0))
    assert (await store.recent(Category.REST_OVER))[0] == line_id(first)


async def test_about_one_in_four_messages_gets_a_punchline() -> None:
    pack = load_pack(None)
    store = MemoryRecentStore()
    rng = random.Random(11)
    punchlines = set(LINES[Category.PUNCHLINE_EN])
    endings = Counter()
    for _ in range(400):
        text = await compose(pack, Category.WORKOUT_START, store, rng)
        base = next(line for line in LINES[Category.WORKOUT_START] if text.startswith(line))
        rest = text[len(base) :].strip()
        assert rest == "" or rest in punchlines, text
        endings["punchline" if rest else "plain"] += 1
    assert 0.18 < endings["punchline"] / 400 < 0.32
