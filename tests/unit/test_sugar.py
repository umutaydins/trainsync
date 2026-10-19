"""ADR 0032: only free sugar counts toward the daily limit."""

import pytest

from trainsync.db.models import FoodGroup
from trainsync.nutrition.sugar import (
    counts_as_free_sugar,
    food_group_from_categories,
    is_intrinsic,
)


@pytest.mark.parametrize(
    ("group", "nova", "counts"),
    [
        (FoodGroup.SUGARY_DRINK, 4, True),  # cola
        (FoodGroup.DESSERT, 3, True),  # baklava
        (FoodGroup.SWEETS, None, True),
        (None, 4, True),  # an ultra-processed food of unknown group
        (FoodGroup.OTHER, 4, True),
        (FoodGroup.FRUIT, 1, False),  # an apple
        (FoodGroup.PLAIN_DAIRY, 4, False),  # plain yoghurt, NOVA 4 in the data: still never
        (FoodGroup.VEGETABLE, 4, False),
        (FoodGroup.OTHER, 3, False),
        (None, None, False),
    ],
)
def test_counts_as_free_sugar(group: FoodGroup | None, nova: int | None, counts: bool) -> None:
    assert counts_as_free_sugar(group, nova) is counts


def test_is_intrinsic_ignores_unknown_values() -> None:
    assert is_intrinsic("fruit")
    assert not is_intrinsic("dessert")
    assert not is_intrinsic("not-a-group")
    assert not is_intrinsic(None)
    assert not counts_as_free_sugar("not-a-group", None)


@pytest.mark.parametrize(
    ("tags", "group"),
    [
        (["en:beverages", "en:sodas"], FoodGroup.SUGARY_DRINK),
        (["en:fruits-based-foods", "en:fruit-juices"], FoodGroup.SUGARY_DRINK),
        (["en:dairies", "en:yogurts", "en:fruit-yogurts"], FoodGroup.DESSERT),
        (["en:dairies", "en:yogurts", "en:plain-yogurts"], FoodGroup.PLAIN_DAIRY),
        (["en:plant-based-foods", "en:fruits", "en:apples"], FoodGroup.FRUIT),
        (["en:snacks", "en:sweet-snacks", "en:confectioneries"], FoodGroup.SWEETS),
        (["en:vegetables"], FoodGroup.VEGETABLE),
        (["en:cereals"], None),
        ([], None),
    ],
)
def test_food_group_from_open_food_facts_categories(
    tags: list[str], group: FoodGroup | None
) -> None:
    assert food_group_from_categories(tags) == group
