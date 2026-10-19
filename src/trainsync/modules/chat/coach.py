"""The coach in chat (P6.11, P6.13; ADR 0030, 0032): guardrails first, then the savage
triggers.

- Distress (guilt spiral, throwing up, not eating, self-hate, binge talk), then pain, injury or
  illness, in every tone, intensity and profanity level: a calm reply from the neutral layer,
  nothing else (no roast, no swearing, no push, no assistant call).
- Savage only (`BOT_INTENSITY=savage`, hardcore, not in soft mode):
  - an unhealthy choice (junk, sugar, fast or fried food, alcohol, cigarettes, staying up late)
    gets a `food_roast` line, then one concrete move for that kind of choice, then the day's
    kcal target, unchanged. The choice is roasted, never the body; nothing suggests eating less
    than the target;
  - an excuse ("I don't feel like it", "tomorrow", …) gets a roast, then one concrete action for
    today: the next program day and its start time, or a short walk.
- `/yumusak`: soft mode for 24 h (normal intensity); `/sert`: back to the configured intensity.

Anything else is not ours (`None`): commands, check-in answers and the assistant handle it.
"""

from datetime import time
from zoneinfo import ZoneInfo

from trainsync.core.clock import Clock
from trainsync.core.localtime import local_today
from trainsync.core.logging import get_logger
from trainsync.modules.chat.common import Incoming, Press, PressResult, Reply, number
from trainsync.modules.chat.read_api import ReadApi, ReadApiError
from trainsync.modules.coach.categories import Category
from trainsync.modules.coach.guardrails import (
    FoodKind,
    Trigger,
    excuse_kind,
    food_kind,
    mentions_distress,
    mentions_pain,
)
from trainsync.modules.coach.mode import SoftModeStore
from trainsync.modules.coach.packs import Key, Messages, NeutralKey
from trainsync.modules.coach.voice import CoachVoice
from trainsync.modules.nutrition.router import DaySummary

log = get_logger(__name__)

COACH_COMMANDS = frozenset({"yumusak", "sert"})
FOOD_MOVES: dict[FoodKind, NeutralKey] = {
    FoodKind.SWEET: NeutralKey.FOOD_MOVE_SWEET,
    FoodKind.FAST_FOOD: NeutralKey.FOOD_MOVE_FAST_FOOD,
    FoodKind.FRIED: NeutralKey.FOOD_MOVE_FRIED,
    FoodKind.ALCOHOL: NeutralKey.FOOD_MOVE_ALCOHOL,
    FoodKind.SMOKING: NeutralKey.FOOD_MOVE_SMOKING,
    FoodKind.LATE: NeutralKey.FOOD_MOVE_LATE,
}


def calm_reply(text: str, msg: Messages) -> str | None:
    """The calm reply to distress or pain, or None. Distress first: "kustum" after a binge needs
    the supportive words, not "see a doctor"."""
    if mentions_distress(text):
        return msg.neutral(NeutralKey.SAFETY_DISTRESS)
    if mentions_pain(text):
        return msg.neutral(NeutralKey.SAFETY_PAIN)
    return None


async def day_target_line(api: ReadApi, msg: Messages, clock: Clock, zone: ZoneInfo) -> str:
    """Today's kcal target, unchanged by any roast, with what is left of it."""
    try:
        summary = await api.nutrition_summary(local_today(clock, zone))
    except ReadApiError:
        return msg.neutral(NeutralKey.FOOD_NO_TARGET)
    return target_line(summary, msg)


def target_line(summary: DaySummary, msg: Messages) -> str:
    if summary.kcal_target is None or summary.kcal_remaining is None:
        return msg.neutral(NeutralKey.FOOD_NO_TARGET)
    remaining = max(summary.kcal_remaining, 0)
    return msg.neutral(
        NeutralKey.FOOD_TARGET,
        target=f"{summary.kcal_target} kcal",
        remaining=f"{number(remaining, 0)} kcal",
    )


class CoachFeature:
    commands = COACH_COMMANDS

    def __init__(
        self,
        api: ReadApi,
        voice: CoachVoice,
        soft: SoftModeStore,
        clock: Clock,
        zone: ZoneInfo,
        msg: Messages,
        default_start: time,
    ) -> None:
        self._api = api
        self._voice = voice
        self._soft = soft
        self._clock = clock
        self._zone = zone
        self._msg = msg
        self._default_start = default_start

    async def command(self, incoming: Incoming, command: str, args: list[str]) -> Reply:
        if command == "yumusak":
            await self._soft.soften()
            log.info("coach_soft_mode", on=True)
            return Reply(self._msg(Key.COACH_SOFT_ON))
        await self._soft.harden()
        log.info("coach_soft_mode", on=False)
        return Reply(self._msg(Key.COACH_SOFT_OFF))

    async def text(self, incoming: Incoming) -> Reply | None:
        calm = calm_reply(incoming.text, self._msg)
        if calm is not None:
            log.info("coach_calm_guard", chat_id=incoming.chat_id)
            return Reply(calm, plain=True)
        trigger = excuse_kind(incoming.text)
        if trigger is None or not await self._voice.savage():
            return None
        log.info("coach_trigger", chat_id=incoming.chat_id, trigger=trigger.value)
        if trigger is Trigger.FOOD:
            kind = food_kind(incoming.text)
            if kind is not None:
                return Reply(await self._food(kind))
        roast = await self._voice.roast(Category.EXCUSE)
        return Reply(f"{roast}\n{await self._action()}")

    async def press(self, press: Press) -> PressResult | None:
        return None

    async def _action(self) -> str:
        """One concrete thing to do today."""
        try:
            day = await self._api.next_day()
        except ReadApiError:
            day = None
        if day is None:
            return self._msg(Key.COACH_ACTION_FALLBACK)
        start = day.start_time or self._default_start
        return self._msg(Key.COACH_ACTION_PLANNED, day=day.day_name, time=f"{start:%H:%M}")

    async def _food(self, kind: FoodKind) -> str:
        """Roast the choice, one concrete move, the day's target unchanged (ADR 0032)."""
        roast = await self._voice.roast(Category.FOOD_ROAST)
        move = self._msg.neutral(FOOD_MOVES[kind])
        target = await day_target_line(self._api, self._msg, self._clock, self._zone)
        return "\n".join([roast, move, target])
