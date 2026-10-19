"""Check-in training steps: one question per planned exercise, or free `bench 80x5x3` lines."""

from datetime import date
from decimal import Decimal

from trainsync.modules.chat.checkin.base import FlowBase
from trainsync.modules.chat.checkin.keyboards import STEP_KG
from trainsync.modules.chat.checkin.state import (
    FlowState,
    Planned,
    set_id,
    workout_client_id,
    workout_id_of,
)
from trainsync.modules.chat.common import Reply, numbered, sets_text
from trainsync.modules.chat.exercises import resolve_exercise
from trainsync.modules.chat.parsing import ParsedSet, ParseError, parse_choice, parse_log
from trainsync.modules.chat.training import todays_workout
from trainsync.modules.coach.packs import Key, NeutralKey
from trainsync.modules.training.workout_schemas import SetIn

# Parsing data, not output: words (tr/en) that end the free-form set logging.
FREEFORM_FINISH_WORDS = frozenset({"done", "finish", "bitti", "bitir", "tamam"})


class WorkoutSteps(FlowBase):
    async def _begin_training(self, chat_id: int, day: date, state: FlowState) -> Reply:
        program_day = await self._api.next_day()
        workout = await todays_workout(self._api, self._clock, self._zone)
        if program_day is None or not program_day.planned:
            state.workout_id = workout.id if workout else None
            return await self._ask(chat_id, day, state, "freeform", [])
        if workout is None:
            workout_id = (
                program_day.open_workout_id
                or (
                    await self._api.start_workout(
                        workout_client_id(day), self._clock(), program_day.day_id
                    )
                ).id
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
        detail = await self._api.workout(workout_id_of(state))
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

    async def _freeform(self, chat_id: int, day: date, state: FlowState, text: str) -> Reply:
        msg = self._msg
        if text.lower() in FREEFORM_FINISH_WORDS:
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
            start_id = workout_client_id(day)
            state.workout_id = (await self._api.start_workout(start_id, self._clock())).id
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

    async def _put_sets(
        self, day: date, state: FlowState, exercise_id: int, sets: list[ParsedSet], *, start: int
    ) -> None:
        workout_id = workout_id_of(state)
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
