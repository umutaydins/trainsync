"""Nutrition and scale commands (P6.8): `/eat`, `/kcal`, `/weight`.

Every text here comes from the tone-free layer (`Messages.neutral`); the scale is never commented
on. The one exception is the savage coach (ADR 0032): an `/eat` log of a high-sugar (more than
`HIGH_SUGAR_PER_100G`) or NOVA 4 food, or a free-sugar item that takes the day's free sugar past
`SUGAR_LIMIT_G`, gets a `food_roast` line about the choice, one concrete move and the day's kcal
target, unchanged. Fruit, vegetables and plain dairy are never roasted for sugar
(`nutrition.sugar`). Days are the owner's local days (`CHECKIN_TZ`); the API is asked for that date
explicitly. `/eat` client ids are `uuid5("tg:{chat}:{update}:eat")`.
"""

from decimal import Decimal
from zoneinfo import ZoneInfo

from trainsync.core.clock import Clock
from trainsync.core.localtime import local_now, local_today
from trainsync.modules.chat.coach import target_line
from trainsync.modules.chat.common import (
    Incoming,
    Pending,
    Press,
    PressResult,
    Reply,
    StateStore,
    client_id,
    kg,
    load_pending,
    number,
    numbered,
    pending_key,
    save_pending,
)
from trainsync.modules.chat.parsing import ParseError, parse_choice, parse_eat, parse_number
from trainsync.modules.chat.read_api import ReadApi, ReadApiError
from trainsync.modules.coach.categories import Category
from trainsync.modules.coach.context import current_sugar_limit, current_zone
from trainsync.modules.coach.packs import Messages, NeutralKey
from trainsync.modules.coach.voice import CoachVoice
from trainsync.modules.nutrition.models import Meal
from trainsync.modules.nutrition.router import FoodOut, LogIn, LogOut
from trainsync.modules.nutrition.sugar import ULTRA_PROCESSED, counts_as_free_sugar, is_intrinsic

NUTRITION_COMMANDS = frozenset({"eat", "kcal", "weight"})
MAX_CHOICES = 8
_MEAL_LABELS = {
    Meal.BREAKFAST: NeutralKey.MEAL_BREAKFAST,
    Meal.LUNCH: NeutralKey.MEAL_LUNCH,
    Meal.DINNER: NeutralKey.MEAL_DINNER,
    Meal.SNACK: NeutralKey.MEAL_SNACK,
}


def meal_at(hour: int) -> Meal:
    """Local hour → meal: 04-10 breakfast, 11-15 lunch, 17-21 dinner, otherwise a snack."""
    if 4 <= hour <= 10:
        return Meal.BREAKFAST
    if 11 <= hour <= 15:
        return Meal.LUNCH
    if 17 <= hour <= 21:
        return Meal.DINNER
    return Meal.SNACK


def food_label(food: FoodOut) -> str:
    return f"{food.name} ({food.brand})" if food.brand else food.name


def pick_food(foods: list[FoodOut], query: str) -> FoodOut | None:
    """One food when the match is clear: the only one, or the only exact name."""
    if len(foods) == 1:
        return foods[0]
    exact = [f for f in foods if f.name.casefold() == query.strip().casefold()]
    return exact[0] if len(exact) == 1 else None


class NutritionCommands:
    commands = NUTRITION_COMMANDS

    def __init__(
        self,
        api: ReadApi,
        store: StateStore,
        clock: Clock,
        zone: ZoneInfo,
        msg: Messages,
        *,
        voice: CoachVoice | None = None,
        sugar_limit_g: float = 50.0,
        high_sugar_per_100g: float = 22.5,
    ) -> None:
        self._api = api
        self._store = store
        self._clock = clock
        self._default_zone = zone
        self._msg = msg
        self._voice = voice
        self._default_sugar_limit_g = sugar_limit_g
        self._high_sugar_per_100g = high_sugar_per_100g

    @property
    def _zone(self) -> ZoneInfo:
        """The user's time zone in this update (ADR 0036), else the configured one."""
        return current_zone(self._default_zone)

    async def command(self, incoming: Incoming, command: str, args: list[str]) -> Reply:
        if command == "eat":
            return Reply(await self.eat(incoming, args))
        if command == "kcal":
            return Reply(await self.kcal())
        return Reply(await self.scale(args))

    async def text(self, incoming: Incoming) -> Reply | None:
        """A number answering the `/eat` food list."""
        pending = await load_pending(self._store, incoming.chat_id)
        if pending is None or pending.kind != "eat":
            return None
        try:
            choice = parse_choice(incoming.text, len(pending.options))
        except ParseError:
            count = len(pending.options)
            return Reply(self._msg.neutral(NeutralKey.CHOICE_INVALID, count=count))
        if choice is None:
            await self._store.delete(pending_key(incoming.chat_id))
            return None
        food_id, name = pending.options[choice]
        grams = Decimal(pending.payload["grams"])
        text = await self._log(incoming.chat_id, pending.update_id, food_id, name, grams)
        await self._store.delete(pending_key(incoming.chat_id))
        return Reply(text)

    async def press(self, press: Press) -> PressResult | None:
        return None

    async def eat(self, incoming: Incoming, args: list[str]) -> str:
        neutral = self._msg.neutral
        try:
            query, grams = parse_eat(args)
        except ParseError:
            return neutral(NeutralKey.EAT_USAGE)
        foods = (await self._api.foods(query, limit=MAX_CHOICES)).items
        if not foods:
            # Nothing stored yet: Open Food Facts (the API caches what it finds).
            foods = (await self._api.food_lookup(query, limit=MAX_CHOICES)).items
        if not foods:
            return neutral(NeutralKey.EAT_NOT_FOUND, query=query)
        food = pick_food(foods, query)
        if food is not None:
            return await self._log(
                incoming.chat_id, incoming.update_id, food.id, food_label(food), grams
            )
        pending = Pending(
            kind="eat",
            update_id=incoming.update_id,
            options=[(f.id, food_label(f)) for f in foods],
            payload={"grams": str(grams)},
        )
        await save_pending(self._store, incoming.chat_id, pending)
        return neutral(NeutralKey.EAT_CHOOSE, choices=numbered([food_label(f) for f in foods]))

    async def _log(
        self, chat_id: int, update_id: int, food_id: int, label: str, grams: Decimal
    ) -> str:
        now = local_now(self._clock, self._zone)
        meal = meal_at(now.hour)
        body = LogIn(date=now.date(), meal=meal, food_id=food_id, grams=float(grams))
        entry = await self._api.put_food_log(client_id(f"tg:{chat_id}:{update_id}:eat"), body)
        saved = self._msg.neutral(
            NeutralKey.EAT_SAVED,
            grams=f"{number(grams, 1)} g",
            food=label,
            meal=self._msg.neutral(_MEAL_LABELS[meal]),
            kcal=f"{number(entry.kcal, 0)} kcal",
        )
        return "\n".join([saved, *await self._roast(entry)])

    async def _roast(self, entry: LogOut) -> list[str]:
        """Savage only: a high-sugar or ultra-processed item, or a free-sugar item that takes the
        day over the sugar limit. Fruit, vegetables and plain dairy are never roasted."""
        if self._voice is None or not await self._voice.savage():
            return []
        if is_intrinsic(entry.food_group):
            return []
        high_sugar = (entry.sugars_100g or 0) > self._high_sugar_per_100g
        high = high_sugar or entry.nova_group == ULTRA_PROCESSED
        free = counts_as_free_sugar(entry.food_group, entry.nova_group) and bool(entry.sugars_g)
        try:
            day = await self._api.nutrition_summary(entry.date)
        except ReadApiError:
            day = None
        limit = current_sugar_limit(self._default_sugar_limit_g)
        over = day is not None and free and day.free_sugars_g > limit
        if not (high or over):
            return []
        neutral = self._msg.neutral
        lines = [await self._voice.roast(Category.FOOD_ROAST)]
        if over and day is not None:
            lines.append(
                neutral(
                    NeutralKey.FOOD_SUGAR_DAY,
                    sugar=f"{number(day.free_sugars_g, 0)} g",
                    limit=f"{number(limit, 0)} g",
                )
            )
        lines.append(neutral(NeutralKey.FOOD_MOVE_LOGGED))
        lines.append(target_line(day, self._msg) if day else neutral(NeutralKey.FOOD_NO_TARGET))
        return lines

    async def kcal(self) -> str:
        neutral = self._msg.neutral
        today = local_today(self._clock, self._zone)
        day = await self._api.nutrition_summary(today)
        lines = [neutral(NeutralKey.KCAL_TITLE, day=self._msg.day(today))]
        if day.entry_count == 0:
            lines.append(neutral(NeutralKey.KCAL_NONE))
            return "\n".join(lines)
        intake = f"{number(day.intake_kcal, 0)} kcal"
        if day.kcal_target is not None and day.kcal_remaining is not None:
            lines.append(
                neutral(
                    NeutralKey.KCAL_INTAKE_TARGET,
                    intake=intake,
                    target=f"{day.kcal_target} kcal",
                    remaining=f"{number(day.kcal_remaining, 0)} kcal",
                    entries=day.entry_count,
                )
            )
        else:
            lines.append(neutral(NeutralKey.KCAL_INTAKE, intake=intake, entries=day.entry_count))
        lines.append(
            neutral(
                NeutralKey.KCAL_MACROS,
                protein=f"{number(day.protein_g, 0)} g",
                carbs=f"{number(day.carbs_g, 0)} g",
                fat_g=f"{number(day.fat_g, 0)} g",
            )
        )
        if not day.macros_complete:
            lines.append(neutral(NeutralKey.KCAL_MACROS_INCOMPLETE))
        return "\n".join(lines)

    async def scale(self, args: list[str]) -> str:
        neutral = self._msg.neutral
        value = parse_number(args[0]) if len(args) == 1 else None
        if value is None or not 0 < value < 500:
            return neutral(NeutralKey.SCALE_USAGE, command="/weight")
        today = local_today(self._clock, self._zone)
        saved = await self._api.put_body_metric(today, value)
        return neutral(
            NeutralKey.SCALE_SAVED, day=self._msg.day(saved.date), value=kg(saved.weight_kg)
        )
