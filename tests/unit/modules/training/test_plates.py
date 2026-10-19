"""P6.3: plate calculator and the GYM_PLATES setting."""

from decimal import Decimal

import pytest

from tests.conftest import make_settings
from trainsync.core.plate_inventory import DEFAULT_INVENTORY, parse_inventory
from trainsync.modules.training.plates import plates_per_side

D = Decimal


def side(*plates: str) -> tuple[Decimal, ...]:
    return tuple(D(p) for p in plates)


@pytest.mark.parametrize(
    ("target", "per_side"),
    [
        ("100", side("25", "15")),
        ("102.5", side("25", "15", "1.25")),
        ("60", side("20")),
        ("22.5", side("1.25")),
        ("20", side()),
        # Everything in the default inventory: 2 * 157.5 + 20.
        (
            "335",
            side(
                "25",
                "25",
                "20",
                "20",
                "15",
                "15",
                "10",
                "10",
                "5",
                "5",
                "2.5",
                "2.5",
                "1.25",
                "1.25",
            ),
        ),
    ],
)
def test_exact_loads(target: str, per_side: tuple[Decimal, ...]) -> None:
    load = plates_per_side(D(target))
    assert load.per_side == per_side
    assert load.achieved_kg == D(target)
    assert (load.exact, load.difference_kg) == (True, 0)


def test_unreachable_target_gives_the_nearest_lower_weight_and_the_difference() -> None:
    load = plates_per_side(D("101"))
    assert (load.per_side, load.achieved_kg, load.difference_kg, load.exact) == (
        side("25", "15"),
        D("100"),
        D("1"),
        False,
    )
    # More than the whole inventory.
    full = plates_per_side(D("400"))
    assert (full.achieved_kg, full.difference_kg) == (D(335), D(65))


def test_inventory_limits_are_respected_and_the_search_is_not_greedy() -> None:
    inventory = {D(25): 1, D(15): 2}
    load = plates_per_side(D(80), D(20), inventory)
    assert load.per_side == side("15", "15")  # greedy would take 25 and stop at 70
    assert load.exact
    only_fives = plates_per_side(D(60), D(20), {D(5): 2})
    assert (only_fives.per_side, only_fives.achieved_kg) == (side("5", "5"), D(40))
    none = plates_per_side(D(60), D(20), {})
    assert (none.per_side, none.achieved_kg) == ((), D(20))


def test_fewest_plates_win() -> None:
    load = plates_per_side(D(60), D(20), {D(10): 2, D(5): 4, D(20): 1})
    assert load.per_side == side("20")


def test_bar_heavier_than_target() -> None:
    load = plates_per_side(D(15), D(20))
    assert (load.per_side, load.achieved_kg, load.difference_kg, load.exact) == (
        (),
        D(20),
        D(-5),
        False,
    )


def test_custom_bar() -> None:
    assert plates_per_side(D(25), D(15)).per_side == side("5")


def test_parse_inventory() -> None:
    assert parse_inventory("25x2, 20x2,1.25X2,10,,5x0") == {
        D(25): 2,
        D(20): 2,
        D("1.25"): 2,
        D(10): 1,
        D(5): 0,
    }
    for bad in ("25x", "x2", "-5x2", "5x-1", "abc"):
        with pytest.raises(ValueError, match="bad plate entry"):
            parse_inventory(bad)


def test_settings_parse_plates_and_default() -> None:
    assert make_settings().gym_plates == DEFAULT_INVENTORY
    assert make_settings().gym_bar_kg == D(20)
    custom = make_settings(gym_plates="20x1,10x3", gym_bar_kg="15")
    assert (custom.gym_plates, custom.gym_bar_kg) == ({D(20): 1, D(10): 3}, D(15))
    with pytest.raises(ValueError, match="bad plate entry"):
        make_settings(gym_plates="heavy")
