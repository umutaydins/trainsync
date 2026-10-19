"""Food log schemas: one entry (grams of a food at a meal) and a day of entries."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from trainsync.modules.nutrition.energy import per_grams, tenth
from trainsync.modules.nutrition.models import Food, FoodGroup, FoodLog, Meal
from trainsync.modules.nutrition.schemas.common import GroupField, Nova, optional_float

MAX_LOG_GRAMS = 5000

LOG_IN_EXAMPLE: dict[str, Any] = {
    "date": "2026-10-14",
    "meal": "breakfast",
    "food_id": 7,
    "grams": 80,
}
LOG_EXAMPLE: dict[str, Any] = {
    "client_id": "0b6f1f9e-4c1e-4a8e-9a43-2f1d8f0c6a11",
    **LOG_IN_EXAMPLE,
    "food_name": "Rolled oats",
    "brand": "Acme",
    "kcal": 297.6,
    "protein_g": 10.8,
    "carbs_g": 47.0,
    "fat_g": 5.6,
    "sugars_g": 0.9,
    "sugars_100g": 1.1,
    "nova_group": 1,
    "food_group": "other",
    "created_at": "2026-10-14T07:12:03Z",
}


class LogIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [LOG_IN_EXAMPLE]})

    date: date
    meal: Meal
    food_id: int
    grams: Annotated[float, Field(gt=0, le=MAX_LOG_GRAMS)]


class LogOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [LOG_EXAMPLE]})

    client_id: uuid.UUID
    date: date
    meal: Meal
    food_id: int
    food_name: str
    brand: str | None
    grams: float
    kcal: float
    protein_g: float | None = Field(description="null when the food's value is unknown")
    carbs_g: float | None = Field(description="null when the food's value is unknown")
    fat_g: float | None = Field(description="null when the food's value is unknown")
    sugars_g: float | None = Field(
        default=None, description="null when the food's value is unknown"
    )
    sugars_100g: float | None = Field(default=None, description="Snapshot; null = unknown")
    nova_group: Nova = None
    food_group: GroupField = None
    created_at: datetime

    @classmethod
    def from_rows(cls, log: FoodLog, food: Food) -> "LogOut":
        def amount(per_100g: Decimal | None) -> float | None:
            return None if per_100g is None else float(tenth(per_grams(per_100g, log.grams)))

        return cls(
            client_id=log.client_id,
            date=log.date,
            meal=Meal(log.meal),
            food_id=food.id,
            food_name=food.name,
            brand=food.brand,
            grams=float(log.grams),
            # Snapshotted at log time: editing the food later does not change this entry.
            kcal=float(tenth(per_grams(log.kcal_100g, log.grams))),
            protein_g=amount(log.protein_100g),
            carbs_g=amount(log.carbs_100g),
            fat_g=amount(log.fat_100g),
            sugars_g=amount(log.sugars_100g),
            sugars_100g=optional_float(log.sugars_100g),
            nova_group=log.nova_group,
            food_group=FoodGroup(log.food_group) if log.food_group else None,
            created_at=log.created_at,
        )


class DayLog(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"date": "2026-10-14", "entries": [LOG_EXAMPLE]}]}
    )

    date: date
    entries: list[LogOut] = Field(description="In meal order, then as logged")
