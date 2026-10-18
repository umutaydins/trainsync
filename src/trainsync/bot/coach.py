"""The coach in chat (P6.11, ADR 0030): guardrails first, then the savage triggers.

- Pain, injury or illness in a message, in every tone and intensity: a calm "rest / see a
  doctor" reply from the neutral layer, nothing else (no roast, no push, no assistant call).
- Savage only (`BOT_INTENSITY=savage`, hardcore, Turkish, not in soft mode):
  - an excuse ("I don't feel like it", "tomorrow", …) gets a roast, then one concrete action for
    today: the next program day and its start time, or a short walk;
  - a craving gets the neutral food line "eat it, log it, stay in your daily target" with
    today's remaining kcal. Food is never roasted.
- `/yumusak`: soft mode for 24 h (normal intensity); `/sert`: back to the configured intensity.

Anything else is not ours (`None`): commands, check-in answers and the assistant handle it.
"""

from datetime import time
from zoneinfo import ZoneInfo

from trainsync.bot.common import Incoming, Press, PressResult, Reply, number
from trainsync.bot.messages import Key, Messages, NeutralKey
from trainsync.bot.read_api import ReadApi, ReadApiError
from trainsync.coach.categories import Category
from trainsync.coach.guardrails import Trigger, excuse_kind, mentions_pain
from trainsync.coach.mode import SoftModeStore
from trainsync.coach.voice import CoachVoice
from trainsync.core.clock import Clock
from trainsync.core.localtime import local_today
from trainsync.core.logging import get_logger

log = get_logger(__name__)

COACH_COMMANDS = frozenset({"yumusak", "sert"})


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
        if mentions_pain(incoming.text):
            log.info("coach_pain_guard", chat_id=incoming.chat_id)
            return Reply(self._msg.neutral(NeutralKey.SAFETY_PAIN))
        trigger = excuse_kind(incoming.text)
        if trigger is None or not await self._voice.savage():
            return None
        log.info("coach_trigger", chat_id=incoming.chat_id, trigger=trigger.value)
        if trigger is Trigger.CRAVING:
            return Reply(await self._craving())
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

    async def _craving(self) -> str:
        """Eat it, log it, stay in the daily target. Never a push to eat less than that."""
        try:
            summary = await self._api.nutrition_summary(local_today(self._clock, self._zone))
        except ReadApiError:
            return self._msg.neutral(NeutralKey.FOOD_CRAVING_NO_TARGET)
        if summary.kcal_target is None or summary.kcal_remaining is None:
            return self._msg.neutral(NeutralKey.FOOD_CRAVING_NO_TARGET)
        remaining = max(summary.kcal_remaining, 0)
        return self._msg.neutral(NeutralKey.FOOD_CRAVING, remaining=f"{number(remaining, 0)} kcal")
