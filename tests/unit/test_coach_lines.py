"""P6.11/P6.12/P6.13: the savage packs (Turkish and English, roast and max pools), the local
override file, rotation and punchlines (ADR 0030, 0031, 0032)."""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

import random
import re
from collections import Counter
from pathlib import Path

import pytest

from tests.support.swears import swears
from trainsync.coach.categories import MESSAGE_CATEGORIES, ROAST_CATEGORIES, Category
from trainsync.coach.guardrails import mentions_distress, mentions_pain, violations
from trainsync.coach.lines import (
    RECENT,
    SAVAGE,
    SAVAGE_MAX,
    LinePack,
    MemoryRecentStore,
    compose,
    line_id,
    load_pack,
    load_packs,
    merge,
    pick,
    read_local,
)
from trainsync.coach.punchlines import MAX_PUNCHLINES, PUNCHLINES
from trainsync.coach.savage_tr import LINES
from trainsync.core.settings import BotLang

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "config" / "messages.local.example.yaml"
# A few names a "quote a famous coach/athlete" line would carry: none may appear.
REAL_PEOPLE = re.compile(r"goggins|rocky|schwarzenegger|arnold|bruce lee|kobe|jordan|ali\b", re.I)


def test_both_languages_have_a_savage_pack() -> None:
    assert set(SAVAGE) == {"en", "tr"}


@pytest.mark.parametrize("lang", ["en", "tr"])
def test_pack_size_and_categories(lang: BotLang) -> None:
    """Fails when a language's pack is missing a category (ADR 0031)."""
    lines = SAVAGE[lang]
    assert set(lines) == set(ROAST_CATEGORIES)
    assert sum(len(lines[c]) for c in MESSAGE_CATEGORIES) >= 60
    assert lines[Category.PUNCHLINE_EN] == PUNCHLINES  # the same add-on in both languages
    assert len(PUNCHLINES) >= 20
    assert all(len(lines[c]) >= 5 for c in MESSAGE_CATEGORIES)
    for texts in lines.values():
        assert len(texts) == len(set(texts)), "duplicate line"


@pytest.mark.parametrize("lang", ["en", "tr"])
def test_every_category_has_max_lines_at_least_as_many_as_roast(lang: BotLang) -> None:
    """Fails when a pack is missing a category in either pool (ADR 0032)."""
    roast, maxed = SAVAGE[lang], SAVAGE_MAX[lang]
    assert set(maxed) == set(Category)
    for category in ROAST_CATEGORIES:
        assert len(maxed[category]) >= len(roast[category]), category
    assert len(roast[Category.FOOD_ROAST]) >= 20
    assert len(maxed[Category.FOOD_ROAST]) >= 20
    assert len(maxed[Category.MAX_OPENER]) >= 10
    assert maxed[Category.PUNCHLINE_EN] == MAX_PUNCHLINES
    for texts in maxed.values():
        assert len(texts) == len(set(texts)), "duplicate line"
    # A max line never doubles as a roast line: `decorate` tells them apart by text.
    assert not {line for t in roast.values() for line in t} & {
        line for t in maxed.values() for line in t
    }


@pytest.mark.parametrize("lang", ["en", "tr"])
def test_every_max_line_swears(lang: BotLang) -> None:
    for category, texts in SAVAGE_MAX[lang].items():
        for line in texts:
            assert swears(line), (category, line)


def test_max_punchlines_are_short_english() -> None:
    for line in MAX_PUNCHLINES:
        assert len(line) <= 45, line
        assert line.isascii(), line


@pytest.mark.parametrize("lang", ["en", "tr"])
@pytest.mark.parametrize("category", list(Category))
@pytest.mark.parametrize("pools", [SAVAGE, SAVAGE_MAX], ids=["roast", "max"])
def test_built_in_lines_respect_the_guardrails(
    lang: BotLang, category: Category, pools: dict[BotLang, dict[Category, tuple[str, ...]]]
) -> None:
    for line in pools[lang].get(category, ()):
        assert violations(line) == [], line
        assert not mentions_pain(line), line
        assert not mentions_distress(line), line
        assert not REAL_PEOPLE.search(line), line
        assert not re.search(r"\d+\s*(?:kg|kcal|kalori|calorie)", line, re.I), line


@pytest.mark.parametrize(
    ("lang", "words"),
    [
        ("tr", ("amına koyayım", "siktir", "amk", "hassiktir", "ulan")),
        ("en", ("fuck", "shit", "damn", "hell", "ass")),
    ],
)
def test_savage_lines_do_swear(lang: BotLang, words: tuple[str, ...]) -> None:
    """The owner asked for it; neither pack may be quietly mild."""
    text = " ".join(line for c in MESSAGE_CATEGORIES for line in SAVAGE[lang][c]).lower()
    for word in words:
        assert word in text, word


def test_the_english_pack_is_english() -> None:
    for pool in (SAVAGE["en"], SAVAGE_MAX["en"]):
        for category in MESSAGE_CATEGORIES:
            for line in pool[category]:
                assert line.isascii(), line


def test_punchlines_are_short_english() -> None:
    for line in LINES[Category.PUNCHLINE_EN]:
        assert len(line) <= 45, line
        assert line.isascii(), line


def test_example_local_file_covers_every_category_and_is_clean() -> None:
    local = read_local(EXAMPLE)
    assert set(local["tr"]) == {c.value for c in ROAST_CATEGORIES}
    assert {"excuse", "language_set", "punchline_en"} <= set(local["en"])
    assert local["en"]["punchline_en"] == local["tr"]["punchline_en"] == ["Do it anyway."]
    for lang in ("tr", "en"):
        pack = merge(SAVAGE[lang], local[lang])
        assert pack.dropped == ()
        assert pack.local_count == sum(len(v) for v in local[lang].values())
    packs = load_packs(EXAMPLE)
    assert "Bundan sonra her mesajda küfür var lan." in packs["tr"].max[Category.EXCUSE]
    assert "Okay, fucking listen:" in packs["en"].max[Category.MAX_OPENER]
    for lang in ("tr", "en"):
        assert "Do it anyway, damn it." in packs[lang].max[Category.PUNCHLINE_EN]
        assert packs[lang].dropped == ()


def test_language_sections_go_to_their_language(tmp_path: Path) -> None:
    path = tmp_path / "messages.local.yaml"
    path.write_text(
        "tr:\n"
        "  excuse:\n"
        '    - "Kalk lan."\n'
        "en:\n"
        "  excuse:\n"
        '    - "Get the fuck up."\n'
        '    - "Fat lazy ass."\n'  # body shaming: dropped, in English too
        "punchline_en:\n"
        '  - "Lift first. Talk later."\n',
        encoding="utf-8",
    )
    packs = load_packs(path)
    assert "Kalk lan." in packs["tr"].lines[Category.EXCUSE]
    assert "Kalk lan." not in packs["en"].lines[Category.EXCUSE]
    assert "Get the fuck up." in packs["en"].lines[Category.EXCUSE]
    assert [d.text for d in packs["en"].dropped] == ["Fat lazy ass."]
    for lang in ("tr", "en"):
        assert "Lift first. Talk later." in packs[lang].lines[Category.PUNCHLINE_EN]


def test_the_max_section_goes_to_the_max_pool(tmp_path: Path) -> None:
    path = tmp_path / "messages.local.yaml"
    path.write_text(
        "tr:\n"
        "  max:\n"
        "    food_roast:\n"
        '      - "Bu ne amk?"\n'
        '      - "Şişko olacaksın."\n'  # body shaming: dropped from max too
        "    max_opener:\n"
        '      - "Lan, dinle:"\n'
        "en:\n"
        "  rest_over:\n"
        '    - "Up."\n'
        "  max:\n"
        "    rest_over:\n"
        '      - "Up, damn it."\n'
        "punchline_en_max:\n"
        '  - "Move your ass."\n',
        encoding="utf-8",
    )
    packs = load_packs(path)
    assert "Bu ne amk?" in packs["tr"].max[Category.FOOD_ROAST]
    assert "Bu ne amk?" not in packs["tr"].lines[Category.FOOD_ROAST]
    assert "Lan, dinle:" in packs["tr"].max[Category.MAX_OPENER]
    assert [d.text for d in packs["tr"].dropped] == ["Şişko olacaksın."]
    assert "Up." in packs["en"].lines[Category.REST_OVER]
    assert "Up, damn it." in packs["en"].max[Category.REST_OVER]
    assert "Up, damn it." not in packs["en"].lines[Category.REST_OVER]
    for lang in ("tr", "en"):
        assert "Move your ass." in packs[lang].max[Category.PUNCHLINE_EN]
        assert "Move your ass." not in packs[lang].lines[Category.PUNCHLINE_EN]


async def test_compose_in_max_takes_both_line_and_punchline_from_the_max_pool() -> None:
    pack = load_pack(None, "en")
    store = MemoryRecentStore()
    rng = random.Random(4)
    for _ in range(80):
        text = await compose(pack, Category.REST_OVER, store, rng, "max")
        base = next(line for line in pack.max[Category.REST_OVER] if text.startswith(line))
        rest = text[len(base) :].strip()
        assert rest == "" or rest in MAX_PUNCHLINES, text


def test_local_lines_are_merged_verbatim_and_bad_ones_dropped(tmp_path: Path) -> None:
    """The first format (categories at the top level) still works and counts as Turkish."""
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
