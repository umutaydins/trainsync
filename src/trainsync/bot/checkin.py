"""The daily check-in conversation (P6.9, ADR 0020): a small finite-state machine.

    status ─┬─ done/partly + program ─→ exercise (one per planned exercise) ─┐
            ├─ done/partly, no program → freeform (`bench 80x5x3` lines, Finish) ┤
            ├─ skipped ─→ reason ─────────────────────────────────────────────┤
            └─ rest / sick ───────────────────────────────────────────────────┤
                                     scale → sleep → energy → done (summary + Edit)

State lives in Redis (`checkin:{chat}:{yyyymmdd}`, 6 h TTL), so the bot can restart mid-flow.
Every button carries `ci:{yyyymmdd}:{seq}:{action}`; `seq` goes up on every step, so a button
from an older message (or a double tap, or a redelivered press) no longer matches and is answered
with a polite "that button is from an earlier question". A text answer redelivered by Telegram
has an `update_id` the state has already seen and is ignored.

Writes are idempotent: sets use `uuid5("checkin:{date}:{exercise_id}:{set_index}")` and the
check-in itself is `PUT /v1/checkins/{date}`, so "edit" and retries overwrite instead of adding.
"""

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from trainsync.api.checkins import CheckinIn
from trainsync.api.training.workouts import PlannedExercise, SetIn
from trainsync.bot.common import (
    Incoming,
    Press,
    PressResult,
    Reply,
    StateStore,
    client_id,
    kg,
    number,
    numbered,
    sets_text,
    thousands,
)
from trainsync.bot.exercises import resolve_exercise
from trainsync.bot.messages import Key, Messages, NeutralKey
from trainsync.bot.parsing import (
    ParsedSet,
    ParseError,
    parse_choice,
    parse_log,
    parse_number,
    parse_sets,
)
from trainsync.bot.read_api import ReadApi
from trainsync.bot.telegram import Button, Keyboard
from trainsync.bot.training import plan_text, record_lines, suggested_load, todays_workout
from trainsync.core.clock import Clock
from trainsync.core.localtime import local_today
from trainsync.db.models import CheckinStatus, Equipment

STATE_TTL_S = 6 * 3600
STEP_KG = Decimal("2.5")
MINUS = chr(0x2212)  # the minus sign, for the "-2.5 kg" button
REPORT_WORDS = frozenset({"report", "rapor"})
FINISH_WORDS = frozenset({"done", "finish", "bitti", "bitir", "tamam"})
STATUS_CODES: dict[str, CheckinStatus] = {
    "done": CheckinStatus.DONE,
    "partial": CheckinStatus.PARTIAL,
    "skipped": CheckinStatus.SKIPPED,
    "rest": CheckinStatus.REST,
    "sick": CheckinStatus.SICK_OR_INJURED,
}
STATUS_BUTTONS: dict[CheckinStatus, Key] = {
    CheckinStatus.DONE: Key.CHECKIN_BTN_DONE,
    CheckinStatus.PARTIAL: Key.CHECKIN_BTN_PARTIAL,
    CheckinStatus.SKIPPED: Key.CHECKIN_BTN_SKIPPED,
    CheckinStatus.REST: Key.CHECKIN_BTN_REST,
    CheckinStatus.SICK_OR_INJURED: Key.CHECKIN_BTN_SICK,
}

Step = Literal["status", "exercise", "freeform", "reason", "scale", "sleep", "energy", "done"]
TEXT_STEPS: frozenset[Step] = frozenset(
    {"exercise", "freeform", "reason", "scale", "sleep", "energy"}
)


class Planned(BaseModel):
    """What the check-in needs of one planned exercise."""

    exercise_id: int
    name: str
    sets: int
    reps: int  # "As planned" logs the bottom of the rep range (ADR 0020)
    plan: str
    suggested: str
    weight_kg: Decimal | None  # None: no suggestion, type the sets

    @classmethod
    def from_planned(cls, planned: PlannedExercise) -> "Planned":
        weight = planned.suggestion.weight_kg
        if weight is None and planned.exercise.equipment == Equipment.BODYWEIGHT:
            weight = Decimal(0)
        return cls(
            exercise_id=planned.exercise.id,
            name=planned.exercise.name,
            sets=planned.sets,
            reps=planned.rep_min,
            plan=plan_text(planned),
            suggested=suggested_load(planned),
            weight_kg=weight,
        )


class FlowState(BaseModel):
    seq: int = 0
    step: Step = "status"
    status: CheckinStatus | None = None
    workout_id: int | None = None
    planned: list[Planned] = Field(default_factory=list)
    index: int = 0
    logged: dict[int, int] = Field(default_factory=dict)  # exercise id → sets stored
    choices: list[tuple[int, str]] = Field(default_factory=list)  # freeform: which exercise?
    choice_sets: str = ""
    reason: str | None = None
    scale_kg: Decimal | None = None
    sleep_hours: Decimal | None = None
    energy: int | None = None
    last_update_id: int = 0


def set_id(day: date, exercise_id: int, set_index: int) -> uuid.UUID:
    """Deterministic client id of a check-in set: answering twice rewrites the same set."""
    return client_id(f"checkin:{day.isoformat()}:{exercise_id}:{set_index}")


def state_key(chat_id: int, day: date) -> str:
    return f"checkin:{chat_id}:{day:%Y%m%d}"


def callback(day: date, seq: int, action: str) -> str:
    return f"ci:{day:%Y%m%d}:{seq}:{action}"


def status_keyboard(msg: Messages, day: date, seq: int) -> Keyboard:
    def button(code: str) -> Button:
        return Button(msg(STATUS_BUTTONS[STATUS_CODES[code]]), callback(day, seq, f"s:{code}"))

    return (
        (button("done"), button("partial"), button("skipped")),
        (button("rest"), button("sick")),
    )


def prompt(msg: Messages, day: date, *, reminder: bool = False) -> Reply:
    """The evening question with the five status buttons (the worker sends it with seq 0)."""
    text = msg(Key.CHECKIN_REMINDER if reminder else Key.CHECKIN_PROMPT)
    return Reply(text, status_keyboard(msg, day, 0))


class CheckinFlow:
    commands = frozenset({"report"})

    def __init__(
        self, api: ReadApi, store: StateStore, clock: Clock, zone: ZoneInfo, msg: Messages
    ) -> None:
        self._api = api
        self._store = store
        self._clock = clock
        self._zone = zone
        self._msg = msg

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
        if len(parts) != 4 or parts[0] != "ci":
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
        if state.step == "exercise" and action in {"p", "+", "-", "x"}:
            return await self._exercise_button(chat_id, day, state, action)
        if state.step == "freeform" and action == "f":
            return await self._after_training(chat_id, day, state, [])
        if state.step in {"reason", "scale", "sleep", "energy"} and action == "k":
            return await self._skip_question(chat_id, day, state)
        if state.step == "energy" and action.startswith("e:") and action[2:] in "12345":
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

    async def _begin_training(self, chat_id: int, day: date, state: FlowState) -> Reply:
        program_day = await self._api.next_day()
        workout = await todays_workout(self._api, self._clock, self._zone)
        if program_day is None or not program_day.planned:
            state.workout_id = workout.id if workout else None
            return await self._ask(chat_id, day, state, "freeform", [])
        if workout is None:
            workout_id = (
                program_day.open_workout_id
                or (await self._api.start_workout(self._clock(), program_day.day_id)).id
            )
        else:
            workout_id = workout.id
        state.workout_id = workout_id
        state.planned = [Planned.from_planned(p) for p in program_day.planned]
        state.index = 0
        return await self._next_exercise(chat_id, day, state, [])

    async def _next_exercise(
        self, chat_id: int, day: date, state: FlowState, lines: list[str]
    ) -> Reply:
        """Show the next planned exercise that has nothing logged today yet."""
        detail = await self._api.workout(_workout_id(state))
        while state.index < len(state.planned):
            current = state.planned[state.index]
            done = [s for s in detail.sets if s.exercise_id == current.exercise_id]
            ours = {set_id(day, current.exercise_id, s.set_index) for s in done}
            if not done or ours == {s.client_id for s in done}:
                break  # nothing logged, or only by an earlier check-in (edit: ask again)
            logged = sets_text([ParsedSet(s.weight_kg, s.reps) for s in done])
            lines.append(self._msg(Key.CHECKIN_ALREADY_LOGGED, name=current.name, sets=logged))
            state.index += 1
        if state.index >= len(state.planned):
            return await self._after_training(chat_id, day, state, lines)
        current = state.planned[state.index]
        lines.append(
            self._msg(
                Key.CHECKIN_EXERCISE,
                index=state.index + 1,
                total=len(state.planned),
                name=current.name,
                plan=current.plan,
                suggested=current.suggested,
            )
        )
        return await self._ask(chat_id, day, state, "exercise", lines)

    async def _exercise_button(
        self, chat_id: int, day: date, state: FlowState, action: str
    ) -> Reply | None:
        current = state.planned[state.index]
        if action == "x":
            state.index += 1
            skipped = [self._msg(Key.CHECKIN_EXERCISE_SKIPPED, name=current.name)]
            return await self._next_exercise(chat_id, day, state, skipped)
        if current.weight_kg is None:
            return None
        weight = current.weight_kg
        if action == "+":
            weight += STEP_KG
        elif action == "-":
            weight = max(Decimal(0), weight - STEP_KG)
        sets = [ParsedSet(weight, current.reps)] * current.sets
        return await self._store_planned(chat_id, day, state, sets)

    async def _store_planned(
        self, chat_id: int, day: date, state: FlowState, sets: list[ParsedSet]
    ) -> Reply:
        current = state.planned[state.index]
        await self._put_sets(day, state, current.exercise_id, sets, start=1)
        state.logged[current.exercise_id] = len(sets)
        state.index += 1
        saved = self._msg(Key.CHECKIN_SETS_SAVED, name=current.name, sets=sets_text(sets))
        return await self._next_exercise(chat_id, day, state, [saved])

    async def _answer_text(self, chat_id: int, day: date, state: FlowState, text: str) -> Reply:
        msg = self._msg
        if state.step == "exercise":
            try:
                sets = parse_sets(text)
            except ParseError:
                await self._save(chat_id, day, state)
                return Reply(msg(Key.CHECKIN_INVALID_SETS), self._keyboard(day, state))
            return await self._store_planned(chat_id, day, state, sets)
        if state.step == "freeform":
            return await self._freeform(chat_id, day, state, text)
        if state.step == "reason":
            state.reason = text[:500] or None
            return await self._ask(chat_id, day, state, "scale", [msg(Key.CHECKIN_REASON_SAVED)])
        return await self._quick_answer(chat_id, day, state, text)

    async def _freeform(self, chat_id: int, day: date, state: FlowState, text: str) -> Reply:
        msg = self._msg
        if text.lower() in FINISH_WORDS:
            return await self._after_training(chat_id, day, state, [])
        if state.choices:
            return await self._freeform_choice(chat_id, day, state, text)
        try:
            query, sets = parse_log(text.removeprefix("/log").split())
        except ParseError:
            await self._save(chat_id, day, state)
            return Reply(msg(Key.CHECKIN_INVALID_SETS), self._keyboard(day, state))
        resolved = await resolve_exercise(self._api, query)
        if resolved.exercise is None:
            if not resolved.candidates:
                await self._save(chat_id, day, state)
                unknown = msg(Key.LOG_UNKNOWN_EXERCISE, query=query)
                return Reply(unknown, self._keyboard(day, state))
            state.choices = [(e.id, e.name) for e in resolved.candidates]
            state.choice_sets = text
            await self._save(chat_id, day, state)
            names = numbered([name for _, name in state.choices])
            return Reply(msg(Key.LOG_CHOOSE_EXERCISE, choices=names))
        return await self._store_freeform(
            chat_id, day, state, resolved.exercise.id, resolved.exercise.name, sets
        )

    async def _freeform_choice(self, chat_id: int, day: date, state: FlowState, text: str) -> Reply:
        try:
            choice = parse_choice(text, len(state.choices))
        except ParseError:
            choice = None
        if choice is None:
            await self._save(chat_id, day, state)
            count = len(state.choices)
            return Reply(self._msg.neutral(NeutralKey.CHOICE_INVALID, count=count))
        exercise_id, name = state.choices[choice]
        _, sets = parse_log(state.choice_sets.removeprefix("/log").split())
        state.choices, state.choice_sets = [], ""
        return await self._store_freeform(chat_id, day, state, exercise_id, name, sets)

    async def _store_freeform(
        self,
        chat_id: int,
        day: date,
        state: FlowState,
        exercise_id: int,
        name: str,
        sets: list[ParsedSet],
    ) -> Reply:
        if state.workout_id is None:
            state.workout_id = (await self._api.start_workout(self._clock())).id
        start = state.logged.get(exercise_id, 0) + 1
        await self._put_sets(day, state, exercise_id, sets, start=start)
        state.logged[exercise_id] = start - 1 + len(sets)
        await self._save(chat_id, day, state)
        saved = self._msg(Key.CHECKIN_SETS_SAVED, name=name, sets=sets_text(sets))
        return Reply(saved, self._keyboard(day, state))

    async def _after_training(
        self, chat_id: int, day: date, state: FlowState, lines: list[str]
    ) -> Reply:
        return await self._ask(chat_id, day, state, "scale", lines)

    async def _skip_question(self, chat_id: int, day: date, state: FlowState) -> Reply:
        if state.step == "reason":
            lines = [self._msg(Key.CHECKIN_SKIPPED_NO_REASON)]
            return await self._ask(chat_id, day, state, "scale", lines)
        return await self._advance_quick(chat_id, day, state, [])

    async def _quick_answer(self, chat_id: int, day: date, state: FlowState, text: str) -> Reply:
        value = parse_number(text)
        if state.step == "scale" and value is not None and 0 < value < 500:
            state.scale_kg = value
        elif state.step == "sleep" and value is not None and value <= 24:
            state.sleep_hours = value.quantize(Decimal("0.1"))
        elif state.step == "energy" and value is not None and value in range(1, 6):
            state.energy = int(value)
        else:
            example = {"scale": "78.4", "sleep": "7.5", "energy": "4"}[state.step]
            await self._save(chat_id, day, state)
            invalid = self._msg.neutral(NeutralKey.CHECKIN_INVALID_NUMBER, example=example)
            return Reply(invalid, self._keyboard(day, state))
        return await self._advance_quick(chat_id, day, state, [])

    async def _advance_quick(
        self, chat_id: int, day: date, state: FlowState, lines: list[str]
    ) -> Reply:
        following: dict[Step, Step] = {"scale": "sleep", "sleep": "energy"}
        if state.step in following:
            return await self._ask(chat_id, day, state, following[state.step], lines)
        return await self._finish(chat_id, day, state, lines)

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

    # ---------------------------------------------------------------- writes

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

    async def _put_sets(
        self, day: date, state: FlowState, exercise_id: int, sets: list[ParsedSet], *, start: int
    ) -> None:
        workout_id = _workout_id(state)
        now = self._clock()
        for offset, parsed in enumerate(sets):
            index = start + offset
            body = SetIn(
                exercise_id=exercise_id,
                set_index=index,
                reps=parsed.reps,
                weight_kg=parsed.weight_kg,
                completed_at=now,
            )
            await self._api.put_set(workout_id, set_id(day, exercise_id, index), body)

    # ---------------------------------------------------------------- state and keyboards

    def _today(self) -> date:
        return local_today(self._clock, self._zone)

    async def _load(self, chat_id: int, day: date) -> FlowState | None:
        raw = await self._store.get(state_key(chat_id, day))
        return None if raw is None else FlowState.model_validate(json.loads(raw))

    async def _save(self, chat_id: int, day: date, state: FlowState) -> None:
        await self._store.set(state_key(chat_id, day), state.model_dump_json(), STATE_TTL_S)

    def _keyboard(self, day: date, state: FlowState) -> Keyboard | None:
        msg, seq = self._msg, state.seq

        def button(text: str, action: str) -> Button:
            return Button(text, callback(day, seq, action))

        skip = button(msg.neutral(NeutralKey.BUTTON_SKIP), "k")
        if state.step == "exercise":
            current = state.planned[state.index]
            rows: list[tuple[Button, ...]] = []
            if current.weight_kg is not None:
                plus = msg(Key.CHECKIN_BTN_STEP, step=f"+{number(STEP_KG)} kg")
                minus = msg(Key.CHECKIN_BTN_STEP, step=f"{MINUS}{number(STEP_KG)} kg")
                rows.append((button(msg(Key.CHECKIN_BTN_AS_PLANNED), "p"),))
                rows.append((button(plus, "+"), button(minus, "-")))
            rows.append((button(msg(Key.CHECKIN_BTN_SKIP_EXERCISE), "x"),))
            return tuple(rows)
        if state.step == "freeform":
            return ((button(msg(Key.CHECKIN_BTN_FINISH), "f"),),)
        if state.step in {"reason", "scale", "sleep"}:
            return ((skip,),)
        if state.step == "energy":
            return (tuple(button(str(n), f"e:{n}") for n in range(1, 6)), (skip,))
        if state.step == "done":
            return ((button(msg(Key.CHECKIN_BTN_EDIT), "edit"),),)
        return None


def _workout_id(state: FlowState) -> int:
    if state.workout_id is None:  # pragma: no cover - set before any set is logged
        raise RuntimeError("check-in step without a workout")
    return state.workout_id
