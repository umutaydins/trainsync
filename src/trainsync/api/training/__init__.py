"""`/v1/training`: exercises, programs, workouts and sets, progress and body metrics."""

from fastapi import APIRouter

from trainsync.api.training import exercises, planning, programs, progress, workouts

ROUTERS: tuple[APIRouter, ...] = (
    exercises.router,
    planning.router,
    programs.router,
    workouts.router,
    progress.router,
)
