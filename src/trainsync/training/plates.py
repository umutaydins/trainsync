"""Plate calculator: which plates go on each side of the bar for a target weight.

Inventory counts are per pair (`{25: 2}` = two 25 kg plates for each side). When the target
cannot be loaded exactly, the nearest lower weight is returned with the difference.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal, InvalidOperation

CENT = Decimal("0.01")
DEFAULT_BAR_KG = Decimal(20)
DEFAULT_INVENTORY: Mapping[Decimal, int] = {
    Decimal(25): 2,
    Decimal(20): 2,
    Decimal(15): 2,
    Decimal(10): 2,
    Decimal(5): 2,
    Decimal("2.5"): 2,
    Decimal("1.25"): 2,
}


@dataclass(frozen=True, slots=True)
class PlateLoad:
    target_kg: Decimal
    bar_kg: Decimal
    per_side: tuple[Decimal, ...]  # heaviest first
    achieved_kg: Decimal

    @property
    def difference_kg(self) -> Decimal:
        """target - achieved: positive when short, negative when the bar alone is heavier."""
        return self.target_kg - self.achieved_kg

    @property
    def exact(self) -> bool:
        return self.difference_kg == 0


def _cents(value: Decimal) -> int:
    return int((value / CENT).to_integral_value(rounding=ROUND_FLOOR))


def plates_per_side(
    target_kg: Decimal,
    bar_kg: Decimal = DEFAULT_BAR_KG,
    inventory: Mapping[Decimal, int] = DEFAULT_INVENTORY,
) -> PlateLoad:
    """The heaviest loadable weight ≤ target, with the fewest plates (heavier plates on ties).

    Exact search over the inventory, not greedy: with 25x1 and 15x2 per side, 30 kg per side is
    15+15, which greedy (25 first) would miss.
    """
    if target_kg <= bar_kg:
        return PlateLoad(target_kg, bar_kg, (), bar_kg)
    need = _cents((target_kg - bar_kg) / 2)
    plates = sorted(
        (plate for plate, pairs in inventory.items() if plate > 0 for _ in range(pairs)),
        reverse=True,
    )
    # best[sum in cents] = plates for one side; processing heaviest first keeps tuples sorted.
    best: dict[int, tuple[Decimal, ...]] = {0: ()}
    for plate in plates:
        weight = _cents(plate)
        for total, load in sorted(best.items(), reverse=True):
            new_total = total + weight
            if new_total > need:
                continue
            candidate = (*load, plate)
            current = best.get(new_total)
            if current is None or _better(candidate, current):
                best[new_total] = candidate
    side = best[max(best)]
    return PlateLoad(target_kg, bar_kg, side, bar_kg + 2 * sum(side, Decimal(0)))


def _better(candidate: tuple[Decimal, ...], current: tuple[Decimal, ...]) -> bool:
    if len(candidate) != len(current):
        return len(candidate) < len(current)
    return candidate > current


def parse_inventory(spec: str) -> dict[Decimal, int]:
    """`"25x2,20x2,1.25x2"` → {25: 2, 20: 2, 1.25: 2} (pairs per plate weight)."""
    inventory: dict[Decimal, int] = {}
    for part in (p.strip() for p in spec.split(",")):
        if not part:
            continue
        weight, sep, count = part.lower().partition("x")
        try:
            plate, pairs = Decimal(weight.strip()), int(count.strip()) if sep else 1
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"bad plate entry {part!r}; expected e.g. 25x2") from exc
        if plate <= 0 or pairs < 0:
            raise ValueError(f"bad plate entry {part!r}; weight > 0 and pairs ≥ 0")
        inventory[plate] = inventory.get(plate, 0) + pairs
    return inventory
