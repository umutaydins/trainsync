"""Training commands (P6.8): `/today`, `/plates`, `/log`, `/done`.

`/log` adds to today's open workout (started on the owner's local day, `CHECKIN_TZ`) or starts
a free one. Set client ids are `uuid5("tg:{chat}:{update}:{n}")`, so a redelivered update writes
the same sets again instead of new ones (ADR 0017).
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from trainsync.api.training.common import ExerciseOut, RecordOut
from trainsync.api.training.workouts import (
    PlannedExercise,
    SetIn,
    WorkoutDetail,
    WorkoutSummary,
)
from trainsync.bot.common import (
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
    sets_text,
    thousands,
)
from trainsync.bot.exercises import resolve_exercise
from trainsync.bot.formatting import duration
from trainsync.bot.messages import Key, Messages, NeutralKey
from trainsync.bot.parsing import ParsedSet, ParseError, parse_choice, parse_log, parse_number
from trainsync.bot.read_api import ReadApi
from trainsync.core.clock import Clock
from trainsync.core.localtime import local_today
from trainsync.db.models import Equipment

TRAINING_COMMANDS = frozenset({"today", "plates", "log", "done"})


# ---------------------------------------------------------------- shared with the check-in


async def todays_workout(api: ReadApi, clock: Clock, zone: ZoneInfo) -> WorkoutSummary | None:
    """The newest unfinished workout started on the local day, if any."""
    today = local_today(clock, zone)
    for workout in (await api.workouts(limit=5)).items:
        if workout.ended_at is None and workout.started_at.astimezone(zone).date() == today:
            return workout
    return None


async def log_sets(
    api: ReadApi,
    workout_id: int,
    exercise_id: int,
    sets: Sequence[ParsedSet],
    ids: Sequence[uuid.UUID],
    now: datetime,
) -> WorkoutDetail:
    """PUT each set under its client id and return the workout afterwards. A set whose id is
    stored already keeps its `set_index`, so a replay rewrites the same rows unchanged."""
    detail = await api.workout(workout_id)
    known = {s.client_id: s.set_index for s in detail.sets}
    next_index = max((s.set_index for s in detail.sets if s.exercise_id == exercise_id), default=0)
    for parsed, cid in zip(sets, ids, strict=True):
        index = known.get(cid)
        if index is None:
            next_index += 1
            index = next_index
        body = SetIn(
            exercise_id=exercise_id,
            set_index=index,
            reps=parsed.reps,
            weight_kg=parsed.weight_kg,
            completed_at=now,
        )
        await api.put_set(workout_id, cid, body)
    return await api.workout(workout_id)


def plan_text(planned: PlannedExercise) -> str:
    reps = (
        str(planned.rep_min)
        if planned.rep_min == planned.rep_max
        else f"{planned.rep_min}-{planned.rep_max}"
    )
    return f"{planned.sets} x {reps}"


def suggested_load(planned: PlannedExercise) -> str:
    weight = planned.suggestion.weight_kg
    if weight is not None:
        return kg(weight)
    return "bw" if planned.exercise.equipment == Equipment.BODYWEIGHT else "—"


def record_lines(records: Sequence[RecordOut], msg: Messages) -> list[str]:
    if not records:
        return []
    lines = [msg(Key.PRS_TITLE)]
    for record in records:
        if record.kind == "weight_for_reps":
            lines.append(
                msg(
                    Key.PR_WEIGHT_FOR_REPS,
                    exercise=record.exercise_name,
                    load=kg(record.value),
                    reps=record.reps or 0,
                )
            )
        elif record.kind == "e1rm":
            lines.append(msg(Key.PR_E1RM, exercise=record.exercise_name, value=kg(record.value)))
        else:
            value = thousands(record.value)
            lines.append(msg(Key.PR_VOLUME, exercise=record.exercise_name, value=value))
    return lines


# ---------------------------------------------------------------- commands


class TrainingCommands:
    commands = TRAINING_COMMANDS

    def __init__(
        self, api: ReadApi, store: StateStore, clock: Clock, zone: ZoneInfo, msg: Messages
    ) -> None:
        self._api = api
        self._store = store
        self._clock = clock
        self._zone = zone
        self._msg = msg

    async def command(self, incoming: Incoming, command: str, args: list[str]) -> Reply:
        if command == "today":
            return Reply(await self.today())
        if command == "plates":
            return Reply(await self.plates(args))
        if command == "log":
            return Reply(await self.log(incoming, args))
        return Reply(await self.done())

    async def text(self, incoming: Incoming) -> Reply | None:
        """A number answering the `/log` exercise list."""
        pending = await load_pending(self._store, incoming.chat_id)
        if pending is None or pending.kind != "log":
            return None
        try:
            choice = parse_choice(incoming.text, len(pending.options))
        except ParseError:
            count = len(pending.options)
            return Reply(self._msg.neutral(NeutralKey.CHOICE_INVALID, count=count))
        if choice is None:
            await self._store.delete(pending_key(incoming.chat_id))
            return None
        exercise_id, name = pending.options[choice]
        _, sets = parse_log(pending.payload["args"].split())
        text = await self._log(incoming.chat_id, pending.update_id, exercise_id, name, sets)
        await self._store.delete(pending_key(incoming.chat_id))
        return Reply(text)

    async def press(self, press: Press) -> PressResult | None:
        return None

    async def today(self) -> str:
        msg = self._msg
        day = await self._api.next_day()
        if day is None:
            return msg(Key.TODAY_NO_PROGRAM)
        lines = [msg(Key.TODAY_TITLE, program=day.program_name, day_name=day.day_name)]
        lines += [
            msg(
                Key.TODAY_EXERCISE,
                name=p.exercise.name,
                plan=plan_text(p),
                suggested=suggested_load(p),
            )
            for p in day.planned
        ]
        if day.open_workout_id is not None:
            workout = await self._api.workout(day.open_workout_id)
            lines.append(msg(Key.TODAY_IN_PROGRESS, count=workout.set_count))
        lines.append(msg(Key.TODAY_FOOTER))
        return "\n".join(lines)

    async def plates(self, args: list[str]) -> str:
        msg = self._msg
        target = parse_number(args[0]) if len(args) == 1 else None
        if target is None or target > 1000:
            return msg(Key.USAGE_PLATES)
        load = await self._api.plates(target)
        per_side = (
            " + ".join(number(p) for p in load.per_side) + " kg"
            if load.per_side
            else msg(Key.PLATES_NONE)
        )
        lines = [msg(Key.PLATES, target=kg(load.target_kg), per_side=per_side, bar=kg(load.bar_kg))]
        if not load.exact:
            lines.append(
                msg(
                    Key.PLATES_INEXACT,
                    achieved=kg(load.achieved_kg),
                    difference=kg(load.difference_kg),
                )
            )
        return "\n".join(lines)

    async def log(self, incoming: Incoming, args: list[str]) -> str:
        msg = self._msg
        try:
            query, sets = parse_log(args)
        except ParseError:
            return msg(Key.USAGE_LOG)
        resolved = await resolve_exercise(self._api, query)
        if resolved.exercise is not None:
            exercise = resolved.exercise
            return await self._log(
                incoming.chat_id, incoming.update_id, exercise.id, exercise.name, sets
            )
        if not resolved.candidates:
            return msg(Key.LOG_UNKNOWN_EXERCISE, query=query)
        await self._ask(incoming, resolved.candidates, " ".join(args))
        names = [e.name for e in resolved.candidates]
        return msg(Key.LOG_CHOOSE_EXERCISE, choices=numbered(names))

    async def _ask(self, incoming: Incoming, candidates: list[ExerciseOut], args: str) -> None:
        pending = Pending(
            kind="log",
            update_id=incoming.update_id,
            options=[(e.id, e.name) for e in candidates],
            payload={"args": args},
        )
        await save_pending(self._store, incoming.chat_id, pending)

    async def _log(
        self, chat_id: int, update_id: int, exercise_id: int, name: str, sets: list[ParsedSet]
    ) -> str:
        now = self._clock()
        workout = await todays_workout(self._api, self._clock, self._zone)
        workout_id = workout.id if workout else (await self._api.start_workout(now)).id
        ids = [client_id(f"tg:{chat_id}:{update_id}:{n}") for n in range(len(sets))]
        detail = await log_sets(self._api, workout_id, exercise_id, sets, ids, now)
        return self._msg(
            Key.LOG_SAVED, exercise=name, sets=sets_text(sets), volume=thousands(detail.volume_kg)
        )

    async def done(self) -> str:
        msg = self._msg
        workout = await todays_workout(self._api, self._clock, self._zone)
        if workout is None:
            return msg(Key.DONE_NO_WORKOUT)
        now = self._clock()
        detail = await self._api.finish_workout(workout.id, now)
        ended = detail.ended_at or now
        lines = [
            msg(
                Key.DONE_SUMMARY,
                count=detail.set_count,
                exercises=detail.exercise_count,
                volume=thousands(detail.volume_kg),
                duration=duration(int((ended - detail.started_at).total_seconds())),
            )
        ]
        lines += record_lines(detail.records, msg)
        return "\n".join(lines)
