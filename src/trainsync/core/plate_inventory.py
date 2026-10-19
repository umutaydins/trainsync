"""The gym's plate inventory setting (`GYM_PLATES`): the default and its parser."""

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

DEFAULT_INVENTORY: Mapping[Decimal, int] = {
    Decimal(25): 2,
    Decimal(20): 2,
    Decimal(15): 2,
    Decimal(10): 2,
    Decimal(5): 2,
    Decimal("2.5"): 2,
    Decimal("1.25"): 2,
}


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
