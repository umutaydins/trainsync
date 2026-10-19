"""P6.1: training math against the hand-computed fixture tests/fixtures/training_math.json."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from trainsync.modules.training import math
from trainsync.modules.training.math import PersonalRecord, PrKind, SetEntry

FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parents[3] / "fixtures" / "training_math.json").read_text(encoding="utf-8")
)


def _dec(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def entries(session: dict[str, Any]) -> list[SetEntry]:
    return [
        SetEntry(
            session=session["id"],
            exercise_id=s["exercise_id"],
            reps=s["reps"],
            weight_kg=Decimal(s["weight_kg"]),
            is_warmup=s.get("is_warmup", False),
        )
        for s in session["sets"]
    ]


SESSIONS = FIXTURE["sessions"]
ALL_SETS = [s for session in SESSIONS for s in entries(session)]


@pytest.mark.parametrize("case", FIXTURE["e1rm"], ids=lambda c: f"{c['weight_kg']}x{c['reps']}")
def test_e1rm(case: dict[str, Any]) -> None:
    assert math.e1rm(Decimal(case["weight_kg"]), case["reps"]) == _dec(case["expected"])


def test_set_volume() -> None:
    assert math.set_volume(5, Decimal("102.5")) == Decimal("512.50")
    assert math.set_volume(12, Decimal(0)) == Decimal("0.00")


@pytest.mark.parametrize("session", SESSIONS, ids=lambda s: s["id"])
def test_session_volume_excludes_warmups(session: dict[str, Any]) -> None:
    assert math.volume(entries(session)) == Decimal(session["volume"])


def test_only_warmups_is_zero_volume_and_no_e1rm() -> None:
    warmup = SetEntry("w", 1, 10, Decimal(40), is_warmup=True)
    assert math.volume([warmup]) == Decimal("0.00")
    assert math.best_e1rm([warmup]) is None
    assert math.best_weight_per_reps([warmup]) == {}


def test_reps_above_twelve_never_set_an_e1rm() -> None:
    sets = [SetEntry("w", 1, 15, Decimal(100)), SetEntry("w", 1, 12, Decimal(60))]
    assert math.best_e1rm(sets) == Decimal("84.00")


def test_best_weight_per_reps() -> None:
    bench = [s for s in ALL_SETS if s.exercise_id == 1]
    expected = {int(r): Decimal(w) for r, w in FIXTURE["best_weight_per_reps"]["1"].items()}
    assert math.best_weight_per_reps(bench) == expected


def test_prs_session_by_session() -> None:
    history: list[SetEntry] = []
    for session in SESSIONS:
        sets = entries(session)
        expected = [
            PersonalRecord(
                exercise_id=pr["exercise_id"],
                kind=PrKind(pr["kind"]),
                value=Decimal(pr["value"]),
                previous=_dec(pr["previous"]),
                reps=pr["reps"],
            )
            for pr in session["prs"]
        ]
        assert math.detect_prs(history, sets) == expected, session["id"]
        history.extend(sets)


def test_a_tie_is_not_a_record() -> None:
    first = [SetEntry("a", 1, 5, Decimal(100))]
    again = [SetEntry("b", 1, 5, Decimal(100))]
    assert math.detect_prs(first, again) == []


def test_weekly_volume_per_primary_muscle() -> None:
    dated = [
        (date.fromisoformat(session["date"]), s) for session in SESSIONS for s in entries(session)
    ]
    muscles = {int(k): v for k, v in FIXTURE["exercises"].items()}
    result = math.weekly_muscle_volume(dated, muscles)
    expected = {
        (date.fromisoformat(row["week"]), row["muscle"]): math.MuscleVolume(
            row["sets"], Decimal(row["volume_kg"])
        )
        for row in FIXTURE["weekly_muscle_volume"]
    }
    assert result == expected
    assert list(result) == list(expected)  # sorted by week, then muscle
