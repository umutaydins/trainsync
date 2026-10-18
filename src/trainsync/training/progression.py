"""Double progression: the weight to use next session for a planned exercise (ADR 0018).

- every working set of the last session reached `rep_max` → add the increment
  (2.5 kg; 5 kg for lower-body exercises);
- the last two sessions both had a working set below `rep_min` → deload by 10 %;
- otherwise keep the weight and add reps.
Warm-up sets are ignored. A weight of 0 (bodyweight) never changes: progress there is reps.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum

from trainsync.training.math import SetEntry, working


class Action(StrEnum):
    START = "start"  # no history: the planned start weight (may be null)
    INCREASE = "increase"
    HOLD = "hold"
    DELOAD = "deload"


@dataclass(frozen=True, slots=True)
class Rules:
    increment_kg: Decimal = Decimal("2.5")
    lower_body_increment_kg: Decimal = Decimal(5)
    deload_factor: Decimal = Decimal("0.9")
    # Deloaded weights are rounded down to what plates can make.
    round_to_kg: Decimal = Decimal("1.25")


@dataclass(frozen=True, slots=True)
class Suggestion:
    action: Action
    weight_kg: Decimal | None
    previous_weight_kg: Decimal | None


def _missed(sets: Sequence[SetEntry], rep_min: int) -> bool:
    return any(s.reps < rep_min for s in sets)


def _round_down(weight: Decimal, step: Decimal) -> Decimal:
    return (weight / step).to_integral_value(rounding=ROUND_FLOOR) * step


def suggest(
    sessions: Sequence[Sequence[SetEntry]],
    rep_min: int,
    rep_max: int,
    *,
    planned_sets: int = 1,
    lower_body: bool = False,
    start_weight_kg: Decimal | None = None,
    auto: bool = True,
    rules: Rules | None = None,
) -> Suggestion:
    """`sessions`: sets of earlier sessions of this exercise, newest first.

    With `auto=False` (progression "none") the last weight is kept. "Every set hit rep_max" needs
    at least `planned_sets` working sets, so stopping early never counts as a full session.
    """
    rules = rules or Rules()
    history = [w for w in (working(s) for s in sessions) if w]
    if not history:
        return Suggestion(Action.START, start_weight_kg, None)
    last = history[0]
    weight = max(s.weight_kg for s in last)
    if not auto or weight == 0:
        return Suggestion(Action.HOLD, weight, weight)
    if len(history) >= 2 and _missed(last, rep_min) and _missed(history[1], rep_min):
        lighter = _round_down(weight * rules.deload_factor, rules.round_to_kg)
        return Suggestion(Action.DELOAD, lighter, weight)
    if len(last) >= planned_sets and all(s.reps >= rep_max for s in last):
        step = rules.lower_body_increment_kg if lower_body else rules.increment_kg
        return Suggestion(Action.INCREASE, weight + step, weight)
    return Suggestion(Action.HOLD, weight, weight)
