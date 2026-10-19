"""`/v1/training`: exercises, programs, workouts and sets, progress and body metrics."""

from fastapi import APIRouter

from trainsync.modules.training.routes import (
    exercises,
    next_day,
    planning,
    programs,
    progress,
    workouts,
)

ROUTERS: tuple[APIRouter, ...] = (
    exercises.router,
    planning.router,
    next_day.router,
    programs.router,
    workouts.router,
    progress.router,
)
