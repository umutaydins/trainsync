"""Field types shared by the nutrition schemas."""

from decimal import Decimal
from typing import Annotated

from pydantic import Field

from trainsync.modules.nutrition.models import FoodGroup

BARCODE_PATTERN = r"^\d{8,14}$"
MAX_KCAL_100G = 1000
GRAMS_PER_100G = 100
NOVA_MIN, NOVA_MAX = 1, 4

Kcal100 = Annotated[float, Field(ge=0, le=MAX_KCAL_100G, description="kcal per 100 g")]
Macro100 = Annotated[
    float | None, Field(ge=0, le=GRAMS_PER_100G, description="g per 100 g; null = unknown")
]
Nova = Annotated[
    int | None,
    Field(
        ge=NOVA_MIN,
        le=NOVA_MAX,
        description="Open Food Facts NOVA group, 4 = ultra-processed; null = unknown",
    ),
]
GroupField = Annotated[
    FoodGroup | None,
    Field(
        description="Decides whether the sugar is free sugar (sweets, dessert, sugary_drink"
        " count; fruit, vegetable, plain_dairy never do); null = unknown"
    ),
]


def optional_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)
