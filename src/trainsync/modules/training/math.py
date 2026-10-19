"""Training math: volume, estimated 1RM, personal records and weekly volume per muscle.

Pure functions over plain values, so the API, the bot and the tests share one definition.
Weights are `Decimal` kilograms (the database stores numeric(6,2)); derived values are rounded to
0.01 kg, half up. Warm-up sets never count toward volume or records.
"""

from collections import defaultdict
from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

CENT = Decimal("0.01")
# Above this many reps Epley overestimates badly, so no e1RM is reported.
E1RM_MAX_REPS = 12


@dataclass(frozen=True, slots=True)
class SetEntry:
    """One logged set, as the math needs it. `session` groups sets of one workout."""

    session: Hashable
    exercise_id: int
    reps: int
    weight_kg: Decimal
    is_warmup: bool = False


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def set_volume(reps: int, weight_kg: Decimal) -> Decimal:
    """reps * weight."""
    return _cents(reps * weight_kg)


def volume(sets: Iterable[SetEntry]) -> Decimal:
    """Total volume of the working sets (warm-ups excluded)."""
    return _cents(sum((s.reps * s.weight_kg for s in sets if not s.is_warmup), Decimal(0)))


def e1rm(weight_kg: Decimal, reps: int) -> Decimal | None:
    """Epley: `w * (1 + reps/30)`; `w` for a single; None for 0 reps or more than 12."""
    if reps < 1 or reps > E1RM_MAX_REPS:
        return None
    if reps == 1:
        return _cents(weight_kg)
    return _cents(weight_kg * (1 + Decimal(reps) / 30))


def working(sets: Iterable[SetEntry]) -> list[SetEntry]:
    return [s for s in sets if not s.is_warmup]


def best_weight_per_reps(sets: Iterable[SetEntry]) -> dict[int, Decimal]:
    """Heaviest working weight lifted for each rep count (reps ≥ 1)."""
    best: dict[int, Decimal] = {}
    for s in working(sets):
        if s.reps >= 1 and s.weight_kg > best.get(s.reps, Decimal(-1)):
            best[s.reps] = s.weight_kg
    return best


def best_e1rm(sets: Iterable[SetEntry]) -> Decimal | None:
    values = [v for s in working(sets) if (v := e1rm(s.weight_kg, s.reps)) is not None]
    return max(values, default=None)


def session_volumes(sets: Iterable[SetEntry]) -> dict[Hashable, Decimal]:
    """Working volume per session, in first-seen session order."""
    by_session: dict[Hashable, list[SetEntry]] = defaultdict(list)
    for s in sets:
        by_session[s.session].append(s)
    return {session: volume(entries) for session, entries in by_session.items()}


def best_session_volume(sets: Iterable[SetEntry]) -> Decimal | None:
    return max(session_volumes(sets).values(), default=None)


class PrKind(StrEnum):
    WEIGHT_FOR_REPS = "weight_for_reps"
    E1RM = "e1rm"
    SESSION_VOLUME = "session_volume"


@dataclass(frozen=True, slots=True)
class PersonalRecord:
    exercise_id: int
    kind: PrKind
    value: Decimal
    previous: Decimal | None
    reps: int | None = None  # for WEIGHT_FOR_REPS


def detect_prs(history: Iterable[SetEntry], session: Iterable[SetEntry]) -> list[PersonalRecord]:
    """Records the new `session` sets beat, per exercise, against all earlier `history`.

    A first-ever performance is a record too (`previous` is None). Ties are not records.
    """
    before: dict[int, list[SetEntry]] = defaultdict(list)
    for s in history:
        before[s.exercise_id].append(s)
    now: dict[int, list[SetEntry]] = defaultdict(list)
    for s in session:
        now[s.exercise_id].append(s)

    records: list[PersonalRecord] = []
    for exercise_id, sets in now.items():
        old = before[exercise_id]
        old_by_reps = best_weight_per_reps(old)
        for reps, weight in sorted(best_weight_per_reps(sets).items()):
            previous = old_by_reps.get(reps)
            if previous is None or weight > previous:
                records.append(
                    PersonalRecord(exercise_id, PrKind.WEIGHT_FOR_REPS, weight, previous, reps)
                )
        records.extend(
            _better(exercise_id, PrKind.E1RM, best_e1rm(sets), best_e1rm(old))
            + _better(exercise_id, PrKind.SESSION_VOLUME, volume(sets), best_session_volume(old))
        )
    return records


def _better(
    exercise_id: int, kind: PrKind, value: Decimal | None, previous: Decimal | None
) -> list[PersonalRecord]:
    if value is None or value <= 0 or (previous is not None and value <= previous):
        return []
    return [PersonalRecord(exercise_id, kind, value, previous)]


@dataclass(frozen=True, slots=True)
class MuscleVolume:
    sets: int
    volume_kg: Decimal


def week_start(day: date) -> date:
    """Monday of the ISO week."""
    return day - timedelta(days=day.weekday())


def weekly_muscle_volume(
    sets: Iterable[tuple[date, SetEntry]], primary_muscle: Mapping[int, str]
) -> dict[tuple[date, str], MuscleVolume]:
    """Working sets and kg per (ISO week start, primary muscle of the exercise)."""
    counts: dict[tuple[date, str], int] = defaultdict(int)
    kilos: dict[tuple[date, str], Decimal] = defaultdict(Decimal)
    for day, s in sets:
        if s.is_warmup:
            continue
        key = (week_start(day), primary_muscle[s.exercise_id])
        counts[key] += 1
        kilos[key] += s.reps * s.weight_kg
    return {key: MuscleVolume(counts[key], _cents(kilos[key])) for key in sorted(counts)}
