"""Shared by the workout and set routes: the 404 lookup and the best-effort coach event."""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.core.errors import error
from trainsync.core.jobs import CoachEvents
from trainsync.core.logging import get_logger
from trainsync.modules.training.models import Workout
from trainsync.modules.training.repository import WorkoutRepository

log = get_logger(__name__)

NOT_FOUND = error("Unknown workout", "workout not found")
WORKOUT_ID_EXAMPLE = 42


async def get_or_404(session: AsyncSession, user_id: int, workout_id: int) -> Workout:
    workout = await WorkoutRepository(session, user_id).get(workout_id)
    if workout is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "workout not found")
    return workout


async def coach_event(events: CoachEvents, job: str, object_id: int) -> None:
    """Best effort (ADR 0030): a queue problem is logged, never fails the write it follows."""
    try:
        await events.coach_event(job, object_id)
    except Exception as exc:
        log.warning("coach_event_not_queued", job=job, object_id=object_id, error=str(exc))
