"""Training tables: exercises, programs, workouts, sets and body metrics (Phase 6).

Every repository is bound to one user (ADR 0035): reads only see that user's rows (plus the
shared built-in exercises), writes stamp the user, and ids of someone else's rows behave as if
they did not exist.
"""

from trainsync.modules.training.repository.body_metrics import BodyMetricRepository
from trainsync.modules.training.repository.exercises import ExerciseRepository
from trainsync.modules.training.repository.programs import ProgramRepository, ProgramTree
from trainsync.modules.training.repository.workouts import (
    SetValues,
    WorkoutKeyset,
    WorkoutRepository,
)

__all__ = [
    "BodyMetricRepository",
    "ExerciseRepository",
    "ProgramRepository",
    "ProgramTree",
    "SetValues",
    "WorkoutKeyset",
    "WorkoutRepository",
]
