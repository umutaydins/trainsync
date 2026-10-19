"""Check-in closing steps: the skip reason, scale, sleep and energy, then the summary."""

from datetime import date
from decimal import Decimal

from trainsync.modules.chat.checkin.base import FlowBase
from trainsync.modules.chat.checkin.state import ENERGY_LEVELS, STATUS_BUTTONS, FlowState, Step
from trainsync.modules.chat.common import Reply, kg, number, thousands
from trainsync.modules.chat.parsing import parse_number
from trainsync.modules.chat.training import record_lines
from trainsync.modules.coach.categories import Category
from trainsync.modules.coach.guardrails import (
    Trigger,
    excuse_kind,
    mentions_distress,
    mentions_pain,
)
from trainsync.modules.coach.packs import Key, NeutralKey

MAX_SCALE_KG = 500  # exclusive: anything heavier is a typo
MAX_SLEEP_HOURS = 24
SLEEP_PRECISION = Decimal("0.1")
NUMBER_EXAMPLES: dict[Step, str] = {"scale": "78.4", "sleep": "7.5", "energy": "4"}
FOLLOWING: dict[Step, Step] = {"scale": "sleep", "sleep": "energy"}


class ClosingSteps(FlowBase):
    async def _reason_reply(self, reason: str) -> list[str]:
        """Distress, pain or illness: calm, in every tone and profanity level (ADR 0030, 0032).
        An excuse in savage: roasted. Anything else: noted."""
        if mentions_distress(reason):
            return [self._msg.neutral(NeutralKey.SAFETY_DISTRESS)]
        if mentions_pain(reason):
            return [self._msg(Key.CHECKIN_SICK_SAVED), self._msg.neutral(NeutralKey.SAFETY_PAIN)]
        if self._voice and await self._voice.savage() and excuse_kind(reason) is Trigger.EXCUSE:
            return [await self._voice.roast(Category.EXCUSE)]
        return [self._msg(Key.CHECKIN_REASON_SAVED)]

    async def _skip_question(self, chat_id: int, day: date, state: FlowState) -> Reply:
        if state.step == "reason":
            if self._voice and await self._voice.savage():
                lines = [await self._voice.roast(Category.MISSED_WORKOUT)]
            else:
                lines = [self._msg(Key.CHECKIN_SKIPPED_NO_REASON)]
            return await self._ask(chat_id, day, state, "scale", lines)
        return await self._advance_quick(chat_id, day, state, [])

    async def _quick_answer(self, chat_id: int, day: date, state: FlowState, text: str) -> Reply:
        value = parse_number(text)
        if state.step == "scale" and value is not None and 0 < value < MAX_SCALE_KG:
            state.scale_kg = value
        elif state.step == "sleep" and value is not None and value <= MAX_SLEEP_HOURS:
            state.sleep_hours = value.quantize(SLEEP_PRECISION)
        elif state.step == "energy" and value is not None and value in ENERGY_LEVELS:
            state.energy = int(value)
        else:
            example = NUMBER_EXAMPLES[state.step]
            await self._save(chat_id, day, state)
            invalid = self._msg.neutral(NeutralKey.CHECKIN_INVALID_NUMBER, example=example)
            return Reply(invalid, self._keyboard(day, state))
        return await self._advance_quick(chat_id, day, state, [])

    async def _advance_quick(
        self, chat_id: int, day: date, state: FlowState, lines: list[str]
    ) -> Reply:
        if state.step in FOLLOWING:
            return await self._ask(chat_id, day, state, FOLLOWING[state.step], lines)
        return await self._finish(chat_id, day, state, lines)

    async def _finish(self, chat_id: int, day: date, state: FlowState, lines: list[str]) -> Reply:
        msg, neutral = self._msg, self._msg.neutral
        saved = await self._put(day, state)
        lines.append(
            msg(Key.CHECKIN_SUMMARY, day=msg.day(day), status=msg(STATUS_BUTTONS[saved.status]))
        )
        if saved.workout_id is not None:
            workout = await self._api.workout(saved.workout_id)
            if workout.set_count:
                volume = thousands(workout.volume_kg)
                lines.append(
                    msg(Key.CHECKIN_SUMMARY_WORKOUT, count=workout.set_count, volume=volume)
                )
                lines += record_lines(workout.records, msg)
        if state.scale_kg is not None:
            lines.append(neutral(NeutralKey.CHECKIN_SUMMARY_SCALE, value=kg(state.scale_kg)))
        if state.sleep_hours is not None:
            hours = f"{number(state.sleep_hours, 1)} h"
            lines.append(neutral(NeutralKey.CHECKIN_SUMMARY_SLEEP, hours=hours))
        if state.energy is not None:
            lines.append(neutral(NeutralKey.CHECKIN_SUMMARY_ENERGY, energy=state.energy))
        streak = (await self._api.checkin_summary(day)).current_streak
        lines.append(msg(Key.CHECKIN_SUMMARY_STREAK, days=streak))
        return await self._ask(chat_id, day, state, "done", lines)
