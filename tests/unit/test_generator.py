"""P6.3: the rule-based program generator over every template, goal and equipment combo."""

import itertools
import json
from importlib import resources

import pytest

from trainsync.db.models import Equipment, MovementPattern, ProgramGoal
from trainsync.training.generator import (
    DOSES,
    MAX_EXERCISES_PER_DAY,
    TEMPLATE_DAYS,
    GeneratorError,
    LibraryExercise,
    Program,
    Request,
    Role,
    Template,
    generate,
)

OPTIONAL_EQUIPMENT = [e for e in Equipment if e is not Equipment.BODYWEIGHT]
EQUIPMENT_SETS = [
    frozenset(combo)
    for size in range(len(OPTIONAL_EQUIPMENT) + 1)
    for combo in itertools.combinations(OPTIONAL_EQUIPMENT, size)
]
MINUTES = (20, 30, 45, 60, 90)


def seed_library() -> list[LibraryExercise]:
    seed = resources.files("trainsync.training").joinpath("seed_exercises.json")
    rows = json.loads(seed.read_text(encoding="utf-8"))
    return [
        LibraryExercise(
            index + 1,
            row["slug"],
            row["name"],
            Equipment(row["equipment"]),
            MovementPattern(row["movement_pattern"]),
        )
        for index, row in enumerate(rows)
    ]


LIBRARY = seed_library()


def assert_valid(program: Program, request: Request) -> None:
    allowed = request.equipment | {Equipment.BODYWEIGHT}
    first, other, accessory = DOSES[request.goal]
    assert len(program.days) == request.days_per_week
    assert len({d.name for d in program.days}) == len(program.days)
    assert program.goal is request.goal
    for day in program.days:
        assert 1 <= len(day.exercises) <= MAX_EXERCISES_PER_DAY, day
        assert day.minutes <= request.session_minutes, day
        ids = [p.exercise.id for p in day.exercises]
        assert len(ids) == len(set(ids)), day
        assert day.exercises[0].role is Role.COMPOUND, day
        for index, planned in enumerate(day.exercises):
            assert planned.exercise.equipment in allowed
            dose = accessory if planned.role is Role.ACCESSORY else first if index == 0 else other
            assert (planned.rep_min, planned.rep_max, planned.rest_seconds) == (
                dose.rep_min,
                dose.rep_max,
                dose.rest_seconds,
            )
            assert 1 <= planned.sets <= dose.sets


def test_every_combination_gives_a_valid_deterministic_program() -> None:
    reversed_library = list(reversed(LIBRARY))
    checked = 0
    for template, goal, equipment, minutes in itertools.product(
        Template, ProgramGoal, EQUIPMENT_SETS, MINUTES
    ):
        for days in TEMPLATE_DAYS[template]:
            request = Request(days, goal, equipment, minutes, template)
            program = generate(request, LIBRARY)
            assert_valid(program, request)
            assert generate(request, LIBRARY) == program
            assert generate(request, reversed_library) == program  # library order is irrelevant
            checked += 1
    assert checked == 5 * 3 * 64 * len(MINUTES)


def test_a_full_gym_hour_gets_a_sensible_upper_lower_program() -> None:
    equipment = frozenset({Equipment.BARBELL, Equipment.DUMBBELL})
    program = generate(Request(4, ProgramGoal.HYPERTROPHY, equipment, 60), LIBRARY)
    assert program.template is Template.UPPER_LOWER
    assert [d.name for d in program.days] == ["Upper A", "Lower A", "Upper B", "Lower B"]
    upper_a = [p.exercise.slug for p in program.days[0].exercises]
    assert upper_a[:4] == ["bench-press", "barbell-row", "overhead-press", "pull-up"]
    lower_a = [p.exercise.slug for p in program.days[1].exercises]
    assert lower_a[:2] == ["back-squat", "romanian-deadlift"]
    first = program.days[0].exercises[0]
    assert (first.sets, first.rep_min, first.rep_max, first.rest_seconds) == (4, 8, 12, 90)
    # A/B days differ.
    assert program.days[0].exercises[0].exercise != program.days[2].exercises[2].exercise
    assert "Upper/Lower" in program.name


def test_short_sessions_drop_accessories_first() -> None:
    equipment = frozenset(OPTIONAL_EQUIPMENT)
    long = generate(Request(3, ProgramGoal.STRENGTH, equipment, 90), LIBRARY)
    short = generate(Request(3, ProgramGoal.STRENGTH, equipment, 30), LIBRARY)
    assert any(p.role is Role.ACCESSORY for d in long.days for p in d.exercises)
    assert all(p.role is Role.COMPOUND for d in short.days for p in d.exercises)
    assert sum(len(d.exercises) for d in short.days) < sum(len(d.exercises) for d in long.days)


def test_default_templates_by_days() -> None:
    expected = {
        2: Template.FULL_BODY,
        3: Template.FULL_BODY,
        4: Template.UPPER_LOWER,
        6: Template.PUSH_PULL_LEGS,
    }
    for days, template in expected.items():
        program = generate(Request(days, ProgramGoal.GENERAL, frozenset(), 60), LIBRARY)
        assert program.template is template


@pytest.mark.parametrize(
    ("days", "template", "minutes", "message"),
    [
        (5, None, 60, "no template for 5 days"),
        (1, None, 60, "no template for 1 days"),
        (3, Template.UPPER_LOWER, 60, "upper_lower takes 4 days"),
        (4, Template.PUSH_PULL_LEGS, 60, "push_pull_legs takes 3 or 6 days"),
        (3, None, 15, "at least 20 minutes"),
    ],
)
def test_unsupported_requests(
    days: int, template: Template | None, minutes: int, message: str
) -> None:
    with pytest.raises(GeneratorError, match=message):
        generate(Request(days, ProgramGoal.GENERAL, frozenset(), minutes, template), LIBRARY)


def test_an_empty_library_is_an_error() -> None:
    with pytest.raises(GeneratorError, match="no exercise in the library fits Full Body A"):
        generate(Request(2, ProgramGoal.GENERAL, frozenset(), 60), [])
