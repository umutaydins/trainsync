"""P6.1: the seeded exercise library (src/trainsync/modules/training/seed_exercises.json)."""

import json
from importlib import resources
from typing import Any

from trainsync.modules.training.models import Equipment, MovementPattern, Muscle


def library() -> list[dict[str, Any]]:
    seed = resources.files("trainsync.modules.training").joinpath("seed_exercises.json")
    rows: list[dict[str, Any]] = json.loads(seed.read_text(encoding="utf-8"))
    return rows


def test_library_is_large_enough_and_slugs_are_unique() -> None:
    rows = library()
    assert len(rows) >= 60
    slugs = [row["slug"] for row in rows]
    assert len(slugs) == len(set(slugs))
    assert all(slug == slug.lower() and " " not in slug for slug in slugs)


def test_every_row_uses_known_values() -> None:
    for row in library():
        assert set(row) == {
            "slug",
            "name",
            "primary_muscle",
            "secondary_muscles",
            "equipment",
            "movement_pattern",
        }, row
        assert Muscle(row["primary_muscle"])
        assert all(Muscle(m) for m in row["secondary_muscles"])
        assert row["primary_muscle"] not in row["secondary_muscles"]
        assert Equipment(row["equipment"])
        assert MovementPattern(row["movement_pattern"])


def test_the_basics_are_there() -> None:
    slugs = {row["slug"] for row in library()}
    for basic in (
        "back-squat",
        "bench-press",
        "deadlift",
        "overhead-press",
        "barbell-row",
        "pull-up",
        "walking-lunge",
        "barbell-curl",
    ):
        assert basic in slugs


def test_every_pattern_has_a_bodyweight_or_dumbbell_option() -> None:
    """The generator (P6.3) must find something for a minimal home setup."""
    rows = library()
    for pattern in MovementPattern:
        options = {r["equipment"] for r in rows if r["movement_pattern"] == pattern}
        assert options & {"bodyweight", "dumbbell"}, pattern
