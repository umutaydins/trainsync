"""What every check-in step needs: dependencies, the local day, state load/save, and moving to the
next question."""

import json
from datetime import date
from zoneinfo import ZoneInfo

from trainsync.core.clock import Clock
from trainsync.core.localtime import local_today
from trainsync.integrations.telegram.client import Keyboard
from trainsync.modules.chat.checkin.keyboards import step_keyboard
from trainsync.modules.chat.checkin.state import STATE_TTL_S, FlowState, Step, state_key
from trainsync.modules.chat.common import Reply, StateStore
from trainsync.modules.chat.read_api import ReadApi
from trainsync.modules.checkin.router import CheckinIn
from trainsync.modules.coach.context import current_zone
from trainsync.modules.coach.packs import Key, Messages, NeutralKey
from trainsync.modules.coach.voice import CoachVoice


class FlowBase:
    def __init__(
        self,
        api: ReadApi,
        store: StateStore,
        clock: Clock,
        zone: ZoneInfo,
        msg: Messages,
        voice: CoachVoice | None = None,
    ) -> None:
        self._api = api
        self._store = store
        self._clock = clock
        self._default_zone = zone
        self._msg = msg
        # Savage roasts for a skip (P6.11, ADR 0030); None = the tone packs only.
        self._voice = voice

    @property
    def _zone(self) -> ZoneInfo:
        """The user's time zone in this update (ADR 0036), else the configured one."""
        return current_zone(self._default_zone)

    def _today(self) -> date:
        return local_today(self._clock, self._zone)

    async def _load(self, chat_id: int, day: date) -> FlowState | None:
        raw = await self._store.get(state_key(chat_id, day))
        return None if raw is None else FlowState.model_validate(json.loads(raw))

    async def _save(self, chat_id: int, day: date, state: FlowState) -> None:
        await self._store.set(state_key(chat_id, day), state.model_dump_json(), STATE_TTL_S)

    def _keyboard(self, day: date, state: FlowState) -> Keyboard | None:
        return step_keyboard(self._msg, day, state)

    async def _ask(
        self, chat_id: int, day: date, state: FlowState, step: Step, lines: list[str]
    ) -> Reply:
        """Move to `step`: new seq (older buttons go stale), save, show its question."""
        state.step = step
        state.seq += 1
        await self._save(chat_id, day, state)
        neutral = self._msg.neutral
        question = {
            "reason": self._msg(Key.CHECKIN_ASK_REASON),
            "freeform": self._msg(Key.CHECKIN_ASK_FREEFORM),
            "scale": neutral(NeutralKey.CHECKIN_ASK_SCALE),
            "sleep": neutral(NeutralKey.CHECKIN_ASK_SLEEP),
            "energy": neutral(NeutralKey.CHECKIN_ASK_ENERGY),
        }.get(step)
        if question is not None:
            lines.append(question)
        return Reply("\n".join(lines), self._keyboard(day, state))

    async def _put(self, day: date, state: FlowState) -> CheckinIn:
        if state.status is None:  # pragma: no cover - every path sets it first
            raise RuntimeError("check-in without a status")
        body = CheckinIn(
            status=state.status,
            workout_id=state.workout_id,
            reason_note=state.reason,
            sleep_hours=state.sleep_hours,
            energy_1_5=state.energy,
            body_weight_kg=state.scale_kg,
        )
        await self._api.put_checkin(day, body)
        return body
