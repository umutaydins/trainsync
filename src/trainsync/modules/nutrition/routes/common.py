"""Shared bits of the `/v1/nutrition` routes: the router factory, today, the food lookup client."""

from datetime import UTC, date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from trainsync.core.clock import Clock
from trainsync.core.errors import Responses, error
from trainsync.integrations.openfoodfacts.client import OpenFoodFactsClient

PREFIX = "/v1/nutrition"
FOOD_NOT_FOUND: Responses = {404: error("Unknown food", "food not found")}


def nutrition_router() -> APIRouter:
    return APIRouter(prefix=PREFIX, tags=["nutrition"])


def get_openfoodfacts(request: Request) -> OpenFoodFactsClient:
    client: OpenFoodFactsClient = request.app.state.openfoodfacts
    return client


OpenFoodFactsDep = Annotated[OpenFoodFactsClient, Depends(get_openfoodfacts)]


def today(clock: Clock) -> date:
    """Days are UTC days, like the rest of the read API (ADR 0019)."""
    return clock().astimezone(UTC).date()


def to_decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))
