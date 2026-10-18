"""The demo seed (P7.9, ADR 0028) is synthetic: code only, deterministic, no real data.

1. Source: the module imports nothing that can read a file, the network or the environment, and
   calls no such builtin; its text holds no e-mail address, URL or phone-number-like string.
2. Values: every text in the built dataset comes from the module's own constants (or the
   "<time of day> <sport>" activity names), and every date lies in the twelve weeks before today.
"""

import ast
import inspect
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from trainsync.demo import seed

SOURCE = inspect.getsource(seed)
TREE = ast.parse(SOURCE)
NOW = datetime(2026, 10, 18, 9, 30, tzinfo=UTC)
ZONE = ZoneInfo("Europe/Istanbul")

ALLOWED_IMPORTS = {
    "random",
    "uuid",
    "dataclasses",
    "datetime",
    "decimal",
    "zoneinfo",
    "trainsync.strava.models",
}
FORBIDDEN_CALLS = {"open", "eval", "exec", "compile", "__import__", "input", "getattr"}


def test_seed_imports_only_pure_modules() -> None:
    imported = set()
    for node in ast.walk(TREE):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported <= ALLOWED_IMPORTS, imported - ALLOWED_IMPORTS


def test_seed_calls_no_io() -> None:
    names = {
        node.func.id
        for node in ast.walk(TREE)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attributes = {node.attr for node in ast.walk(TREE) if isinstance(node, ast.Attribute)}
    assert not names & FORBIDDEN_CALLS
    assert not attributes & {"read_text", "read_bytes", "environ", "getenv", "urlopen", "now"}


def test_seed_source_has_no_personal_looking_strings() -> None:
    assert not re.search(r"[\w.+-]+@[\w-]+\.\w+", SOURCE), "e-mail address"
    assert not re.search(r"https?://", SOURCE), "URL"
    assert not re.search(r"\+\d[\d -]{6,}|\(\d{3}\) ?\d{3}", SOURCE), "phone number"


def _texts(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, (list, tuple, set, frozenset)):
        return set().union(*(_texts(v) for v in value)) if value else set()
    if isinstance(value, dict):
        return _texts(list(value.keys())) | _texts(list(value.values()))
    return set()


def _module_constants() -> set[str]:
    constants: set[str] = set()
    for name, value in vars(seed).items():
        if name.isupper():
            constants |= _texts(value)
    for _, _, exercises in seed.PROGRAM_DAYS:
        constants |= {e.slug for e in exercises}
    return constants


def test_every_text_value_comes_from_the_module_constants() -> None:
    data = seed.build_dataset(NOW, ZONE)
    constants = _module_constants()
    sports = {sport for sport, *_ in seed.CARDIO} | {"Weight Training"}
    activity_name = re.compile(rf"(Morning|Afternoon|Evening) ({'|'.join(sports)})")

    texts = {a.sport_type for a in data.activities}
    texts |= {w.notes for w in data.workouts} | {s.slug for w in data.workouts for s in w.sets}
    texts |= {c.status for c in data.checkins} | {c.reason_note or "" for c in data.checkins}
    texts |= {f.name for f in data.foods} | {f.food for f in data.food_logs}
    texts |= {f.meal for f in data.food_logs}
    statuses = {"done", "partial", "skipped", "rest", "sick_or_injured"}
    assert texts - constants - statuses - {""} == set()
    assert all(activity_name.fullmatch(a.name) for a in data.activities)
    # Strava JSON beyond the typed fields would be a sign of copied real data.
    assert all(set(a.raw()) == set(type(a).model_fields) for a in data.activities)


def test_dataset_is_deterministic_and_in_the_last_twelve_weeks() -> None:
    first = seed.build_dataset(NOW, ZONE)
    assert first == seed.build_dataset(NOW, ZONE)
    today = NOW.astimezone(ZONE).date()
    start = today - timedelta(weeks=seed.WEEKS)
    assert first.today == today
    assert all(start <= c.date < today for c in first.checkins)
    assert len(first.checkins) == seed.WEEKS * 7
    assert all(start <= d < today for d in first.body_weights)
    assert all(start <= f.date <= today for f in first.food_logs)
    assert {f.meal for f in first.food_logs if f.date == today} == {"breakfast"}
    assert all(a.start_date <= NOW for a in first.activities)
    assert min(a.start_date for a in first.activities).date() >= start - timedelta(days=1)


def test_dataset_is_rich_enough_for_the_dashboard() -> None:
    data = seed.build_dataset(NOW, ZONE)
    last_week = NOW - timedelta(days=7)
    assert len([a for a in data.activities if a.start_date >= last_week]) >= 3
    assert len(data.workouts) >= seed.WEEKS * 3
    assert {c.status for c in data.checkins} >= {"done", "rest", "skipped"}
    assert len({f.date for f in data.food_logs}) >= seed.WEEKS * 6
    # Linked check-ins point at workouts of the dataset; weights trend down.
    workouts = {w.client_id for w in data.workouts}
    assert all(c.workout in workouts for c in data.checkins if c.workout)
    weights = [kg for _, kg in sorted(data.body_weights.items())]
    assert weights[0] > weights[-1] > Decimal(70)


def test_a_later_day_slides_the_window() -> None:
    later = seed.build_dataset(NOW + timedelta(days=1), ZONE)
    assert later.checkins[-1].date == NOW.astimezone(ZONE).date()
