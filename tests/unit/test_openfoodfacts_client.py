"""P6.4: the Open Food Facts client against a respx fake."""

from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest
import respx

from tests.conftest import make_settings
from tests.support.openfoodfacts import (
    OFF,
    SEARCH,
    found,
    not_found,
    product,
    product_url,
    search_results,
)
from trainsync.nutrition.off_client import (
    OffProduct,
    OpenFoodFactsClient,
    OpenFoodFactsUnavailableError,
    parse_product,
)

BARCODE = "8690000000017"


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def off(http: httpx.AsyncClient) -> OpenFoodFactsClient:
    return OpenFoodFactsClient(http, make_settings())


def test_tests_never_point_at_the_real_api() -> None:
    assert make_settings().openfoodfacts_base_url == OFF


@respx.mock
async def test_product_by_barcode_with_user_agent_and_timeout(off: OpenFoodFactsClient) -> None:
    route = respx.get(product_url(BARCODE)).mock(return_value=found(product()))
    result = await off.product(BARCODE)
    assert result == OffProduct(
        barcode=BARCODE,
        name="Rolled oats",
        brand="Acme",
        kcal_100g=Decimal("372.0"),
        protein_100g=Decimal("13.5"),
        carbs_100g=Decimal("58.7"),
        fat_100g=Decimal("7.0"),
    )
    request = route.calls.last.request
    assert request.headers["User-Agent"].startswith("trainsync/")
    assert "+https://" in request.headers["User-Agent"]
    assert request.extensions["timeout"] == {"connect": 3.0, "read": 3.0, "write": 3.0, "pool": 3.0}
    assert "nutriments" in request.url.params["fields"]


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        not_found(BARCODE),
        httpx.Response(200, json={"code": BARCODE, "status": 0}),
        found(product(**{"energy-kcal_100g": None})),  # no kcal: unusable
    ],
)
async def test_unknown_or_unusable_product_is_none(
    off: OpenFoodFactsClient, response: httpx.Response
) -> None:
    respx.get(product_url(BARCODE)).mock(return_value=response)
    assert await off.product(BARCODE) is None


@respx.mock
@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout("slow"),
        httpx.ConnectError("refused"),
        httpx.Response(503),
        httpx.Response(429),
        httpx.Response(200, text="<html>maintenance</html>"),
        httpx.Response(200, json=["not", "an", "object"]),
    ],
)
async def test_failures_raise_unavailable(
    off: OpenFoodFactsClient, failure: httpx.Response | Exception
) -> None:
    route = respx.get(product_url(BARCODE))
    if isinstance(failure, Exception):
        route.mock(side_effect=failure)
    else:
        route.mock(return_value=failure)
    with pytest.raises(OpenFoodFactsUnavailableError):
        await off.product(BARCODE)
    assert route.call_count == 1  # no retries: the lookup is interactive


@respx.mock
async def test_search_keeps_only_usable_products(off: OpenFoodFactsClient) -> None:
    route = respx.get(SEARCH).mock(
        return_value=search_results(
            product(code="1111111111111", name="Oat milk"),
            product(code="12", name="bad barcode"),
            product(code="2222222222222", name="  "),
            {"code": "3333333333333", "product_name": "no nutriments"},
            product(
                code="4444444444444", name="kJ only", **{"energy-kcal_100g": None}, energy_100g=1569
            ),
            "not an object",
        )
    )
    results = await off.search("oat", limit=5)
    assert [(p.barcode, p.kcal_100g) for p in results] == [
        ("1111111111111", Decimal("372.0")),
        ("4444444444444", Decimal("375.0")),  # 1569 kJ / 4.184
    ]
    params = route.calls.last.request.url.params
    assert (params["search_terms"], params["page_size"], params["json"]) == ("oat", "5", "1")


@respx.mock
async def test_search_without_products_list_is_empty(off: OpenFoodFactsClient) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, json={"count": 0}))
    assert await off.search("nothing") == []


def test_parse_product_drops_out_of_range_values() -> None:
    parsed = parse_product(
        product(proteins_100g=140, fat_100g="abc", carbohydrates_100g="12.25", brands="")
    )
    assert parsed is not None
    assert (parsed.protein_100g, parsed.fat_100g, parsed.carbs_100g, parsed.brand) == (
        None,
        None,
        Decimal("12.2"),
        None,
    )
    assert parse_product(product(**{"energy-kcal_100g": 2500})) is None
    assert parse_product(product(**{"energy-kcal_100g": True})) is None
    assert parse_product(product(name="x" * 300)) == parse_product(product(name="x" * 200))
