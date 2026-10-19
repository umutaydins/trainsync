"""The check-in entry points: the `/report` command, text answers and button presses.

The steps live in `workout_steps.py` (training) and `closing_steps.py` (reason, scale, sleep,
energy, summary); state and ids in `state.py`, keyboards in `keyboards.py`.
"""

from datetime import date

from trainsync.modules.chat.checkin.closing_steps import ClosingSteps
from trainsync.modules.chat.checkin.keyboards import status_keyboard
from trainsync.modules.chat.checkin.state import (
    CALLBACK_PREFIX,
    ENERGY_LEVELS,
    SKIPPABLE_STEPS,
    STATUS_CODES,
    TEXT_STEPS,
    FlowState,
)
from trainsync.modules.chat.checkin.workout_steps import WorkoutSteps
from trainsync.modules.chat.common import Incoming, Press, PressResult, Reply
from trainsync.modules.chat.parsing import ParseError, parse_sets
from trainsync.modules.checkin.models import CheckinStatus
from trainsync.modules.coach.packs import Key

REPORT_WORDS = frozenset({"report", "rapor"})
MAX_REASON_LENGTH = 500
EXERCISE_ACTIONS = frozenset({"p", "+", "-", "x"})
ENERGY_ACTIONS = frozenset(f"e:{n}" for n in ENERGY_LEVELS)


class CheckinFlow(WorkoutSteps, ClosingSteps):
    commands = frozenset({"report"})

    # ---------------------------------------------------------------- Feature

    async def command(self, incoming: Incoming, command: str, args: list[str]) -> Reply:
        return await self._start(incoming.chat_id, incoming.update_id)

    async def text(self, incoming: Incoming) -> Reply | None:
        day = self._today()
        state = await self._load(incoming.chat_id, day)
        if state is not None and state.step in TEXT_STEPS:
            if incoming.update_id <= state.last_update_id:
                return Reply("")  # a redelivered message: already handled, stay silent
            state.last_update_id = incoming.update_id
            return await self._answer_text(incoming.chat_id, day, state, incoming.text.strip())
        if incoming.text.strip().lower() in REPORT_WORDS:
            return await self._start(incoming.chat_id, incoming.update_id)
        return None

    async def press(self, press: Press) -> PressResult | None:
        parts = press.data.split(":", 3)
        if len(parts) != 4 or parts[0] != CALLBACK_PREFIX:
            return None
        _, day_text, seq_text, action = parts
        day = self._today()
        state = await self._load(press.chat_id, day) or FlowState()
        if day_text != f"{day:%Y%m%d}" or seq_text != str(state.seq):
            return PressResult(toast=self._msg(Key.CHECKIN_STALE))
        reply = await self._answer_press(press.chat_id, day, state, action)
        if reply is None:
            return PressResult(toast=self._msg(Key.CHECKIN_STALE))
        return PressResult(reply=reply, accepted=True)

    # ---------------------------------------------------------------- transitions

    async def _start(self, chat_id: int, update_id: int) -> Reply:
        day = self._today()
        old = await self._load(chat_id, day)
        state = FlowState(seq=(old.seq + 1) if old else 1, last_update_id=update_id)
        await self._save(chat_id, day, state)
        return Reply(self._msg(Key.CHECKIN_PROMPT), status_keyboard(self._msg, day, state.seq))

    async def _answer_press(
        self, chat_id: int, day: date, state: FlowState, action: str
    ) -> Reply | None:
        if action == "edit" and state.step == "done":
            return await self._start(chat_id, state.last_update_id)
        if state.step == "status" and action.startswith("s:"):
            status = STATUS_CODES.get(action[2:])
            return None if status is None else await self._chose(chat_id, day, state, status)
        if state.step == "exercise" and action in EXERCISE_ACTIONS:
            return await self._exercise_button(chat_id, day, state, action)
        if state.step == "freeform" and action == "f":
            return await self._after_training(chat_id, day, state, [])
        if state.step in SKIPPABLE_STEPS and action == "k":
            return await self._skip_question(chat_id, day, state)
        if state.step == "energy" and action in ENERGY_ACTIONS:
            state.energy = int(action[2:])
            return await self._finish(chat_id, day, state, [])
        return None

    async def _chose(
        self, chat_id: int, day: date, state: FlowState, status: CheckinStatus
    ) -> Reply:
        state.status = status
        await self._put(day, state)  # stored right away: no reminder once answered
        if status in (CheckinStatus.DONE, CheckinStatus.PARTIAL):
            return await self._begin_training(chat_id, day, state)
        if status == CheckinStatus.SKIPPED:
            return await self._ask(chat_id, day, state, "reason", [])
        key = Key.CHECKIN_REST_SAVED if status == CheckinStatus.REST else Key.CHECKIN_SICK_SAVED
        return await self._ask(chat_id, day, state, "scale", [self._msg(key)])

    async def _answer_text(self, chat_id: int, day: date, state: FlowState, text: str) -> Reply:
        if state.step == "exercise":
            try:
                sets = parse_sets(text)
            except ParseError:
                await self._save(chat_id, day, state)
                return Reply(self._msg(Key.CHECKIN_INVALID_SETS), self._keyboard(day, state))
            return await self._store_planned(chat_id, day, state, sets)
        if state.step == "freeform":
            return await self._freeform(chat_id, day, state, text)
        if state.step == "reason":
            state.reason = text[:MAX_REASON_LENGTH] or None
            return await self._ask(chat_id, day, state, "scale", await self._reason_reply(text))
        return await self._quick_answer(chat_id, day, state, text)
