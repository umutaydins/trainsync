"""`/v1/training/programs`: training programs with their days and planned exercises."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.core.deps import SessionmakerDep
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.training.models import Program, ProgramDay, ProgramExercise
from trainsync.modules.training.program_schemas import (
    PlannedExerciseOut,
    ProgramDayOut,
    ProgramIn,
    ProgramList,
    ProgramOut,
    ProgramSummary,
)
from trainsync.modules.training.repository import ExerciseRepository, ProgramRepository, ProgramTree

router = APIRouter(prefix="/v1/training", tags=["training"])

NOT_FOUND = error("Unknown program", "program not found")
UNKNOWN_EXERCISE = error("A planned exercise does not exist", "unknown exercise ids: [999]")
PROGRAM_ID_EXAMPLE = 3


async def load_program(session: AsyncSession, user_id: int, program_id: int) -> ProgramOut:
    tree = await ProgramRepository(session, user_id).tree(program_id)
    if tree is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "program not found")
    return await program_out(session, user_id, tree)


async def program_out(session: AsyncSession, user_id: int, tree: ProgramTree) -> ProgramOut:
    ids = sorted({e.exercise_id for _, planned in tree.days for e in planned})
    exercises = await ExerciseRepository(session, user_id).by_ids(ids)
    await session.flush()
    await session.refresh(tree.program)  # `activate` updates in bulk
    summary = ProgramSummary.from_row(tree.program)
    return ProgramOut(
        **summary.model_dump(),
        days=[
            ProgramDayOut(
                id=day.id,
                day_index=day.day_index,
                name=day.name,
                weekday=day.weekday,
                start_time=day.start_time,
                exercises=[
                    PlannedExerciseOut.from_row(p, exercises[p.exercise_id]) for p in planned
                ],
            )
            for day, planned in tree.days
        ],
    )


async def _rows(
    session: AsyncSession, user_id: int, body: ProgramIn
) -> list[tuple[ProgramDay, list[ProgramExercise]]]:
    wanted = {e.exercise_id for day in body.days for e in day.exercises}
    known = await ExerciseRepository(session, user_id).by_ids(sorted(wanted))
    missing = sorted(wanted - known.keys())
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown exercise ids: {missing}")
    return [
        (
            ProgramDay(
                day_index=index, name=day.name, weekday=day.weekday, start_time=day.start_time
            ),
            [
                ProgramExercise(
                    exercise_id=e.exercise_id,
                    sets=e.sets,
                    rep_min=e.rep_min,
                    rep_max=e.rep_max,
                    rest_seconds=e.rest_seconds,
                    start_weight_kg=e.start_weight_kg,
                    progression=e.progression,
                )
                for e in day.exercises
            ],
        )
        for index, day in enumerate(body.days)
    ]


@router.get(
    "/programs",
    summary="List programs",
    description="Every program, newest first, without days.",
    response_model=ProgramList,
    responses={**UNAUTHORIZED},
)
async def list_programs(principal: CurrentUser, sessionmaker: SessionmakerDep) -> ProgramList:
    async with sessionmaker() as session:
        rows = await ProgramRepository(session, principal.user_id).all()
    return ProgramList(items=[ProgramSummary.from_row(r) for r in rows])


@router.post(
    "/programs",
    summary="Create a program",
    description=(
        "A program with its days (in order) and planned exercises (in order). The program "
        "generator's preview (`POST /programs/generate`) has a `program` field that can be sent "
        "here unchanged. New programs are inactive."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=ProgramOut,
    responses={**UNAUTHORIZED, 400: UNKNOWN_EXERCISE},
)
async def create_program(
    principal: CurrentUser, sessionmaker: SessionmakerDep, body: ProgramIn
) -> ProgramOut:
    async with sessionmaker.begin() as session:
        days = await _rows(session, principal.user_id, body)
        program = await ProgramRepository(session, principal.user_id).add(
            Program(name=body.name, goal=body.goal, days_per_week=len(days), weeks=body.weeks),
            days,
        )
        return await load_program(session, principal.user_id, program.id)


@router.get(
    "/programs/active",
    summary="Get the active program",
    description="The one active program with its days, or `404` when none is active.",
    response_model=ProgramOut,
    responses={**UNAUTHORIZED, 404: error("No active program", "no active program")},
)
async def get_active_program(principal: CurrentUser, sessionmaker: SessionmakerDep) -> ProgramOut:
    async with sessionmaker() as session:
        program = await ProgramRepository(session, principal.user_id).active()
        if program is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no active program")
        return await load_program(session, principal.user_id, program.id)


@router.get(
    "/programs/{program_id}",
    summary="Get a program",
    description="One program with its days and planned exercises.",
    response_model=ProgramOut,
    responses={**UNAUTHORIZED, 404: NOT_FOUND},
)
async def get_program(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    program_id: Annotated[int, Path(examples=[PROGRAM_ID_EXAMPLE])],
) -> ProgramOut:
    async with sessionmaker() as session:
        return await load_program(session, principal.user_id, program_id)


@router.put(
    "/programs/{program_id}",
    summary="Replace a program",
    description=(
        "Replaces name, goal, weeks and all days. Logged workouts stay; their link to a "
        "replaced program day becomes null."
    ),
    response_model=ProgramOut,
    responses={**UNAUTHORIZED, 400: UNKNOWN_EXERCISE, 404: NOT_FOUND},
)
async def replace_program(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    program_id: Annotated[int, Path(examples=[PROGRAM_ID_EXAMPLE])],
    body: ProgramIn,
) -> ProgramOut:
    async with sessionmaker.begin() as session:
        repo = ProgramRepository(session, principal.user_id)
        program = await repo.get(program_id)
        if program is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "program not found")
        days = await _rows(session, principal.user_id, body)
        program.name, program.goal, program.weeks = body.name, body.goal, body.weeks
        program.days_per_week = len(days)
        await repo.replace_days(program_id, days)
        return await load_program(session, principal.user_id, program_id)


@router.delete(
    "/programs/{program_id}",
    summary="Delete a program",
    description="Deletes the program and its days; logged workouts stay.",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**UNAUTHORIZED, 404: NOT_FOUND},
)
async def delete_program(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    program_id: Annotated[int, Path(examples=[PROGRAM_ID_EXAMPLE])],
) -> Response:
    async with sessionmaker.begin() as session:
        if not await ProgramRepository(session, principal.user_id).delete(program_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "program not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/programs/{program_id}/activate",
    summary="Activate a program",
    description="Makes this the only active program (idempotent).",
    response_model=ProgramOut,
    responses={**UNAUTHORIZED, 404: NOT_FOUND},
)
async def activate_program(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    program_id: Annotated[int, Path(examples=[PROGRAM_ID_EXAMPLE])],
) -> ProgramOut:
    async with sessionmaker.begin() as session:
        repo = ProgramRepository(session, principal.user_id)
        if await repo.get(program_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "program not found")
        await repo.activate(program_id)
        return await load_program(session, principal.user_id, program_id)
