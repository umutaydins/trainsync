"""Fake Open Food Facts responses for respx (tests never reach the real API)."""

from typing import Any

import httpx

# Same host as OPENFOODFACTS_BASE_URL in tests/conftest.py TEST_ENV.
OFF = "http://openfoodfacts.invalid"
SEARCH = f"{OFF}/cgi/search.pl"


def product_url(barcode: str) -> str:
    return f"{OFF}/api/v2/product/{barcode}.json"


def product(
    code: str = "8690000000017",
    name: str = "Rolled oats",
    brands: str = "Acme, Acme Foods",
    **nutriments: Any,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "energy-kcal_100g": 372,
        "proteins_100g": 13.5,
        "carbohydrates_100g": 58.7,
        "fat_100g": 7,
    }
    values.update(nutriments)
    return {"code": code, "product_name": name, "brands": brands, "nutriments": values}


def found(item: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"code": item["code"], "status": 1, "product": item})


def not_found(code: str) -> httpx.Response:
    return httpx.Response(404, json={"code": code, "status": 0, "status_verbose": "not found"})


def search_results(*items: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"count": len(items), "page": 1, "products": list(items)})
