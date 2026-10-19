"""Food schemas: stored foods, manual entries, edits and the Open Food Facts lookup."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from trainsync.modules.nutrition.models import Food, FoodGroup, FoodSource
from trainsync.modules.nutrition.repository import FoodView
from trainsync.modules.nutrition.schemas.common import (
    BARCODE_PATTERN,
    MAX_KCAL_100G,
    GroupField,
    Kcal100,
    Macro100,
    Nova,
    optional_float,
)

MAX_NAME_LENGTH = 200

FOOD_EXAMPLE: dict[str, Any] = {
    "id": 7,
    "name": "Rolled oats",
    "brand": "Acme",
    "barcode": "8690000000017",
    "kcal_100g": 372.0,
    "protein_100g": 13.5,
    "carbs_100g": 58.7,
    "fat_100g": 7.0,
    "sugars_100g": 1.1,
    "nova_group": 1,
    "food_group": "other",
    "source": "openfoodfacts",
    "favorite": True,
}
FOOD_IN_EXAMPLE: dict[str, Any] = {
    "name": "Chicken breast, cooked",
    "brand": None,
    "barcode": None,
    "kcal_100g": 165,
    "protein_100g": 31,
    "carbs_100g": 0,
    "fat_100g": 3.6,
    "favorite": False,
}


class FoodOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [FOOD_EXAMPLE]})

    id: int
    name: str
    brand: str | None
    barcode: str | None
    kcal_100g: float
    protein_100g: float | None = Field(description="null = unknown")
    carbs_100g: float | None = Field(description="null = unknown")
    fat_100g: float | None = Field(description="null = unknown")
    sugars_100g: float | None = Field(default=None, description="null = unknown")
    nova_group: Nova = None
    food_group: GroupField = None
    source: FoodSource = Field(description="`openfoodfacts` rows are cached lookups")
    favorite: bool

    @classmethod
    def from_view(cls, view: FoodView) -> "FoodOut":
        return cls.from_row(view.food, favorite=view.favorite)

    @classmethod
    def from_row(cls, row: Food, *, favorite: bool = False) -> "FoodOut":
        return cls(
            id=row.id,
            name=row.name,
            brand=row.brand,
            barcode=row.barcode,
            kcal_100g=float(row.kcal_100g),
            protein_100g=optional_float(row.protein_100g),
            carbs_100g=optional_float(row.carbs_100g),
            fat_100g=optional_float(row.fat_100g),
            sugars_100g=optional_float(row.sugars_100g),
            nova_group=row.nova_group,
            food_group=FoodGroup(row.food_group) if row.food_group else None,
            source=FoodSource(row.source),
            favorite=favorite,
        )


class FoodIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [FOOD_IN_EXAMPLE]})

    name: Annotated[str, Field(min_length=1, max_length=MAX_NAME_LENGTH)]
    brand: Annotated[str | None, Field(max_length=MAX_NAME_LENGTH)] = None
    barcode: Annotated[str | None, Field(pattern=BARCODE_PATTERN)] = None
    kcal_100g: Kcal100
    protein_100g: Macro100 = None
    carbs_100g: Macro100 = None
    fat_100g: Macro100 = None
    sugars_100g: Macro100 = None
    nova_group: Nova = None
    food_group: GroupField = None
    favorite: bool = False


class FoodPatch(BaseModel):
    """Only the fields sent are changed."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"kcal_100g": 380, "protein_100g": 13}]}
    )

    name: Annotated[str | None, Field(min_length=1, max_length=MAX_NAME_LENGTH)] = None
    brand: Annotated[str | None, Field(max_length=MAX_NAME_LENGTH)] = None
    kcal_100g: Annotated[float | None, Field(ge=0, le=MAX_KCAL_100G)] = None
    protein_100g: Macro100 = None
    carbs_100g: Macro100 = None
    fat_100g: Macro100 = None
    sugars_100g: Macro100 = None
    nova_group: Nova = None
    food_group: GroupField = None


class FoodList(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [FOOD_EXAMPLE]}]})

    items: list[FoodOut]


RemoteStatus = Literal["ok", "cached", "not_found", "unavailable", "disabled"]


class FoodLookup(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"items": [FOOD_EXAMPLE], "remote": "ok"}]}
    )

    items: list[FoodOut]
    remote: RemoteStatus = Field(
        description=(
            "Open Food Facts outcome: `ok` (asked, results cached), `cached` (barcode already "
            "stored, not asked), `not_found`, `unavailable` (timeout / error: local results "
            "only), `disabled` (`OPENFOODFACTS_ENABLED=false`: local results only)"
        )
    )
