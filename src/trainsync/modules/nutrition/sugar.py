"""Which sugar counts toward the daily limit (ADR 0032).

WHO's 50 g/day applies to *free* sugars: added sugar plus honey, syrups and juice, not the sugar
inside whole fruit, vegetables or plain milk. Logged foods only carry total sugar, so the food's
group decides: sweets, desserts and sugary drinks count, an ultra-processed (NOVA 4) food counts,
and fruit, vegetables and plain dairy never do, whatever their NOVA group. Anything else (or
unknown) does not count; a guess would roast plain foods.
"""

from collections.abc import Iterable

from trainsync.modules.nutrition.models import FoodGroup

ULTRA_PROCESSED = 4  # NOVA group
FREE_SUGAR_GROUPS = frozenset({FoodGroup.SWEETS, FoodGroup.DESSERT, FoodGroup.SUGARY_DRINK})
INTRINSIC_SUGAR_GROUPS = frozenset({FoodGroup.FRUIT, FoodGroup.VEGETABLE, FoodGroup.PLAIN_DAIRY})

# Open Food Facts `categories_tags` → group, first match wins: the sweet groups come first so a
# fruit juice or a fruit yoghurt is not taken for fruit or plain dairy.
OFF_CATEGORY_GROUPS: tuple[tuple[FoodGroup, frozenset[str]], ...] = (
    (
        FoodGroup.SUGARY_DRINK,
        frozenset(
            {
                "en:sodas",
                "en:sweetened-beverages",
                "en:fruit-juices",
                "en:fruit-nectars",
                "en:energy-drinks",
                "en:iced-teas",
                "en:flavoured-milks",
                "en:syrups",
            }
        ),
    ),
    (
        FoodGroup.DESSERT,
        frozenset(
            {
                "en:desserts",
                "en:dairy-desserts",
                "en:frozen-desserts",
                "en:ice-creams",
                "en:pastries",
                "en:cakes",
                "en:flavoured-yogurts",
                "en:fruit-yogurts",
            }
        ),
    ),
    (
        FoodGroup.SWEETS,
        frozenset(
            {
                "en:sweets",
                "en:confectioneries",
                "en:candies",
                "en:chocolates",
                "en:biscuits",
                "en:sweet-spreads",
                "en:honeys",
                "en:jams",
                "en:sugars",
            }
        ),
    ),
    (FoodGroup.FRUIT, frozenset({"en:fruits", "en:fresh-fruits", "en:dried-fruits"})),
    (FoodGroup.VEGETABLE, frozenset({"en:vegetables", "en:fresh-vegetables", "en:legumes"})),
    (
        FoodGroup.PLAIN_DAIRY,
        frozenset({"en:plain-yogurts", "en:natural-yogurts", "en:milks", "en:cheeses"}),
    ),
)


def food_group_from_categories(tags: Iterable[str]) -> FoodGroup | None:
    """The group of an Open Food Facts product; None when no known category matches."""
    present = set(tags)
    for group, categories in OFF_CATEGORY_GROUPS:
        if present & categories:
            return group
    return None


def _group(value: str | None) -> FoodGroup | None:
    try:
        return FoodGroup(value) if value is not None else None
    except ValueError:
        return None


def is_intrinsic(food_group: str | None) -> bool:
    """Fruit, vegetables, plain dairy: their sugar is never roasted."""
    return _group(food_group) in INTRINSIC_SUGAR_GROUPS


def counts_as_free_sugar(food_group: str | None, nova_group: int | None) -> bool:
    """Does this food's sugar count toward `SUGAR_LIMIT_G`?"""
    group = _group(food_group)
    if group in INTRINSIC_SUGAR_GROUPS:
        return False
    return group in FREE_SUGAR_GROUPS or nova_group == ULTRA_PROCESSED
