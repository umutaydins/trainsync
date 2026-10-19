"""P6.3: double progression on fixtures (hit, miss once, miss twice → deload)."""

from decimal import Decimal

from trainsync.modules.training.math import SetEntry
from trainsync.modules.training.progression import Action, Rules, Suggestion, suggest

D = Decimal


def session(weight: str, *reps: int, warmup: bool = False) -> list[SetEntry]:
    return [SetEntry("s", 1, r, D(weight), is_warmup=warmup) for r in reps]


def test_no_history_starts_at_the_planned_weight() -> None:
    assert suggest([], 8, 12, start_weight_kg=D(60)) == Suggestion(Action.START, D(60), None)
    assert suggest([], 8, 12) == Suggestion(Action.START, None, None)
    # Warm-ups alone are no history.
    assert suggest([session("40", 10, warmup=True)], 8, 12).action is Action.START


def test_every_set_at_rep_max_adds_the_increment() -> None:
    hit = [session("80", 12, 12, 12) + session("40", 5, warmup=True)]
    assert suggest(hit, 8, 12, planned_sets=3) == Suggestion(Action.INCREASE, D("82.5"), D(80))
    assert suggest(hit, 8, 12, planned_sets=3, lower_body=True).weight_kg == D(85)
    custom = Rules(increment_kg=D(1), lower_body_increment_kg=D("2.5"))
    assert suggest(hit, 8, 12, rules=custom).weight_kg == D(81)
    assert suggest(hit, 8, 12, lower_body=True, rules=custom).weight_kg == D("82.5")


def test_fewer_sets_than_planned_is_not_a_full_hit() -> None:
    assert suggest([session("80", 12, 12)], 8, 12, planned_sets=3).action is Action.HOLD


def test_within_the_range_holds() -> None:
    assert suggest([session("80", 12, 11, 10)], 8, 12) == Suggestion(Action.HOLD, D(80), D(80))


def test_missing_rep_min_once_holds() -> None:
    history = [session("80", 8, 7, 6), session("77.5", 10, 10, 9)]
    assert suggest(history, 8, 12) == Suggestion(Action.HOLD, D(80), D(80))


def test_missing_rep_min_twice_in_a_row_deloads_ten_percent() -> None:
    history = [session("80", 8, 7, 6), session("80", 7, 6, 6)]
    # 80 * 0.9 = 72 → rounded down to a 1.25 step: 71.25.
    assert suggest(history, 8, 12) == Suggestion(Action.DELOAD, D("71.25"), D(80))
    assert suggest([session("100", 4), session("100", 3)], 5, 5).weight_kg == D(90)


def test_heaviest_working_set_is_the_session_weight() -> None:
    assert suggest([session("80", 12) + session("85", 12)], 8, 12).weight_kg == D("87.5")


def test_manual_progression_and_bodyweight_keep_the_weight() -> None:
    hit = [session("80", 12, 12, 12)]
    assert suggest(hit, 8, 12, auto=False) == Suggestion(Action.HOLD, D(80), D(80))
    pull_ups = [session("0", 12, 12, 12)]
    assert suggest(pull_ups, 8, 12) == Suggestion(Action.HOLD, D(0), D(0))
