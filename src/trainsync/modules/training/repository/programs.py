"""Programs with their days and planned exercises; one active program per user."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.training.models import Program, ProgramDay, ProgramExercise


@dataclass(frozen=True, slots=True)
class ProgramTree:
    program: Program
    days: list[tuple[ProgramDay, list[ProgramExercise]]]


class ProgramRepository:
    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    async def get(self, program_id: int) -> Program | None:
        return await self._session.scalar(
            select(Program).where(Program.id == program_id, Program.user_id == self._user_id)
        )

    async def all(self) -> list[Program]:
        stmt = (
            select(Program)
            .where(Program.user_id == self._user_id)
            .order_by(Program.created_at.desc(), Program.id.desc())
        )
        return list(await self._session.scalars(stmt))

    async def active(self) -> Program | None:
        return await self._session.scalar(
            select(Program).where(Program.active, Program.user_id == self._user_id)
        )

    async def tree(self, program_id: int) -> ProgramTree | None:
        program = await self.get(program_id)
        if program is None:
            return None
        days = list(
            await self._session.scalars(
                select(ProgramDay)
                .where(ProgramDay.program_id == program_id, ProgramDay.user_id == self._user_id)
                .order_by(ProgramDay.day_index)
            )
        )
        exercises = await self.day_exercises([d.id for d in days])
        return ProgramTree(program, [(d, exercises.get(d.id, [])) for d in days])

    async def day(self, program_day_id: int) -> ProgramDay | None:
        return await self._session.scalar(
            select(ProgramDay).where(
                ProgramDay.id == program_day_id, ProgramDay.user_id == self._user_id
            )
        )

    async def day_exercises(self, day_ids: Sequence[int]) -> dict[int, list[ProgramExercise]]:
        rows = await self._session.scalars(
            select(ProgramExercise)
            .where(
                ProgramExercise.program_day_id.in_(day_ids),
                ProgramExercise.user_id == self._user_id,
            )
            .order_by(ProgramExercise.program_day_id, ProgramExercise.position)
        )
        grouped: dict[int, list[ProgramExercise]] = {}
        for row in rows:
            grouped.setdefault(row.program_day_id, []).append(row)
        return grouped

    async def add(
        self, program: Program, days: Sequence[tuple[ProgramDay, Sequence[ProgramExercise]]]
    ) -> Program:
        """Insert a program with its days and exercises (ids are assigned on flush)."""
        program.user_id = self._user_id
        self._session.add(program)
        await self._session.flush()
        await self._add_days(program.id, days)
        return program

    async def replace_days(
        self, program_id: int, days: Sequence[tuple[ProgramDay, Sequence[ProgramExercise]]]
    ) -> None:
        """Swap all days and exercises of a program (workouts keep their history; their
        `program_day_id` becomes null)."""
        await self._session.execute(
            delete(ProgramDay).where(
                ProgramDay.program_id == program_id, ProgramDay.user_id == self._user_id
            )
        )
        await self._add_days(program_id, days)

    async def _add_days(
        self, program_id: int, days: Sequence[tuple[ProgramDay, Sequence[ProgramExercise]]]
    ) -> None:
        for day, exercises in days:
            day.program_id = program_id
            day.user_id = self._user_id
            self._session.add(day)
            await self._session.flush()
            for position, exercise in enumerate(exercises):
                exercise.program_day_id = day.id
                exercise.position = position
                exercise.user_id = self._user_id
                self._session.add(exercise)
        await self._session.flush()

    async def activate(self, program_id: int) -> None:
        """Make this the user's only active program."""
        mine = Program.user_id == self._user_id
        await self._session.execute(
            update(Program)
            .where(mine, Program.active, Program.id != program_id)
            .values(active=False)
        )
        await self._session.execute(
            update(Program).where(mine, Program.id == program_id).values(active=True)
        )

    async def delete(self, program_id: int) -> bool:
        result = await self._session.execute(
            delete(Program)
            .where(Program.id == program_id, Program.user_id == self._user_id)
            .returning(Program.id)
        )
        return result.scalar_one_or_none() is not None
