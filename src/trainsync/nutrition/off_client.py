"""The only module that talks to Open Food Facts (ADR 0019).

Public API, no key. Every request identifies the app with `OPENFOODFACTS_USER_AGENT`, uses the
process's shared `httpx.AsyncClient` and an explicit whole-request timeout
(`OPENFOODFACTS_TIMEOUT_S`, 3 s). No retries: the lookup is interactive, and on a timeout,
a network error, a 5xx or an unreadable body it raises `OpenFoodFactsUnavailableError` so the caller
can answer with local results instead.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

from trainsync.core.logging import get_logger
from trainsync.core.settings import Settings

log = get_logger(__name__)

BARCODE = re.compile(r"^\d{8,14}$")
FIELDS = "code,product_name,product_name_en,generic_name,brands,nutriments,nova_group"
KJ_PER_KCAL = Decimal("4.184")
MAX_NAME = 200


class OpenFoodFactsUnavailableError(Exception):
    """Timeout, network error, 5xx or an unreadable body."""


@dataclass(frozen=True, slots=True)
class OffProduct:
    barcode: str
    name: str
    brand: str | None
    kcal_100g: Decimal
    protein_100g: Decimal | None
    carbs_100g: Decimal | None
    fat_100g: Decimal | None
    sugars_100g: Decimal | None = None
    nova_group: int | None = None  # 1-4 (4 = ultra-processed); None = unknown


class OpenFoodFactsClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._base_url = settings.openfoodfacts_base_url.rstrip("/")
        self._headers = {"User-Agent": settings.openfoodfacts_user_agent}
        self._timeout = httpx.Timeout(settings.openfoodfacts_timeout_s)
        self.enabled = settings.openfoodfacts_enabled

    async def product(self, barcode: str) -> OffProduct | None:
        """The product with this barcode; None if OFF does not know it or lacks its kcal."""
        body = await self._get(f"/api/v2/product/{barcode}.json", {"fields": FIELDS})
        if body is None or body.get("status") != 1:
            return None
        product = body.get("product")
        return parse_product(product) if isinstance(product, Mapping) else None

    async def search(self, query: str, limit: int = 20) -> list[OffProduct]:
        """Full-text search; products without a barcode, name or kcal are skipped."""
        params = {
            "search_terms": query,
            "search_simple": "1",
            "action": "process",
            "json": "1",
            "page_size": str(limit),
            "fields": FIELDS,
        }
        body = await self._get("/cgi/search.pl", params)
        products = body.get("products") if body is not None else None
        if not isinstance(products, list):
            return []
        parsed = (parse_product(p) for p in products if isinstance(p, Mapping))
        return [p for p in parsed if p is not None]

    async def _get(self, path: str, params: Mapping[str, str]) -> Mapping[str, object] | None:
        """JSON body, None on a 404 (unknown product)."""
        try:
            response = await self._http.get(
                self._base_url + path, params=params, headers=self._headers, timeout=self._timeout
            )
        except httpx.HTTPError as exc:
            log.warning("openfoodfacts_unavailable", path=path, error=type(exc).__name__)
            raise OpenFoodFactsUnavailableError(type(exc).__name__) from exc
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        if response.status_code != httpx.codes.OK:
            log.warning("openfoodfacts_unavailable", path=path, status=response.status_code)
            raise OpenFoodFactsUnavailableError(f"HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            log.warning("openfoodfacts_unavailable", path=path, error="invalid JSON")
            raise OpenFoodFactsUnavailableError("invalid JSON") from exc
        if not isinstance(body, Mapping):
            raise OpenFoodFactsUnavailableError("unexpected body")
        return body


def _number(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _macro(nutriments: Mapping[str, object], key: str) -> Decimal | None:
    value = _number(nutriments.get(key))
    if value is None or not 0 <= value <= 100:
        return None
    return value.quantize(Decimal("0.1"))


def _nova(product: Mapping[str, object]) -> int | None:
    value = _number(product.get("nova_group"))
    if value is None or value != value.to_integral_value() or not 1 <= value <= 4:
        return None
    return int(value)


def _kcal(nutriments: Mapping[str, object]) -> Decimal | None:
    kcal = _number(nutriments.get("energy-kcal_100g"))
    if kcal is None:
        kilojoules = _number(nutriments.get("energy_100g"))  # OFF's `energy` is in kJ
        kcal = kilojoules / KJ_PER_KCAL if kilojoules is not None else None
    if kcal is None or not 0 <= kcal <= 1000:
        return None
    return kcal.quantize(Decimal("0.1"))


def _text(product: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = product.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:MAX_NAME]
    return None


def parse_product(product: Mapping[str, object]) -> OffProduct | None:
    """An OFF product as we store it; None when it lacks a valid barcode, a name or kcal."""
    code = product.get("code")
    name = _text(product, "product_name", "product_name_en", "generic_name")
    nutriments = product.get("nutriments")
    if not isinstance(code, str) or not BARCODE.match(code) or name is None:
        return None
    if not isinstance(nutriments, Mapping):
        return None
    kcal = _kcal(nutriments)
    if kcal is None:
        return None
    brands = _text(product, "brands")
    return OffProduct(
        barcode=code,
        name=name,
        brand=brands.split(",")[0].strip() if brands else None,
        kcal_100g=kcal,
        protein_100g=_macro(nutriments, "proteins_100g"),
        carbs_100g=_macro(nutriments, "carbohydrates_100g"),
        fat_100g=_macro(nutriments, "fat_100g"),
        sugars_100g=_macro(nutriments, "sugars_100g"),
        nova_group=_nova(product),
    )
