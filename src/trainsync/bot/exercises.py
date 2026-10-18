"""Exercise names as typed in Telegram → library exercises.

A small alias table covers gym shorthand (`dl`, `ohp`, `rdl`); anything else is searched with
`GET /v1/training/exercises?q=` and matched on the slug or name: exact first, then prefix. More
than one candidate left means the owner picks from a numbered list.
"""

import re
from dataclasses import dataclass

from trainsync.api.training.common import ExerciseOut
from trainsync.bot.read_api import ReadApi

MAX_CHOICES = 8

ALIASES: dict[str, str] = {
    "bench": "bench-press",
    "bp": "bench-press",
    "incline": "incline-bench-press",
    "cgbp": "close-grip-bench-press",
    "squat": "back-squat",
    "squats": "back-squat",
    "frontsquat": "front-squat",
    "legpress": "leg-press",
    "dl": "deadlift",
    "deadlift": "deadlift",
    "rdl": "romanian-deadlift",
    "ohp": "overhead-press",
    "press": "overhead-press",
    "row": "barbell-row",
    "rows": "barbell-row",
    "pullup": "pull-up",
    "pullups": "pull-up",
    "chinup": "chin-up",
    "chinups": "chin-up",
    "dips": "dip",
    "pushup": "push-up",
    "pushups": "push-up",
    "curl": "barbell-curl",
    "curls": "barbell-curl",
    "pulldown": "lat-pulldown",
    "latpulldown": "lat-pulldown",
    "facepull": "face-pull",
    "lateral": "lateral-raise",
    "laterals": "lateral-raise",
    "hipthrust": "hip-thrust",
    "lunge": "walking-lunge",
    "lunges": "walking-lunge",
    "calf": "standing-calf-raise",
    "barfiks": "pull-up",
    "\u015f\u0131nav": "push-up",  # Turkish for push-up
}


@dataclass(frozen=True, slots=True)
class Resolved:
    """Exactly one exercise, or candidates to choose from (empty: nothing matched)."""

    exercise: ExerciseOut | None
    candidates: list[ExerciseOut]


def _slugish(text: str) -> str:
    return re.sub(r"[\W_]+", "-", text.lower()).strip("-")


async def resolve_exercise(api: ReadApi, query: str) -> Resolved:
    wanted = _slugish(query)
    alias = ALIASES.get(wanted.replace("-", ""))
    if alias is not None:
        found = [e for e in (await api.exercises(alias)).items if e.slug == alias]
        if found:
            return Resolved(found[0], [])
    items = (await api.exercises(query.strip())).items
    if not items and "-" in wanted:
        items = (await api.exercises(wanted)).items
    exact = [e for e in items if e.slug == wanted or _slugish(e.name) == wanted]
    if len(exact) == 1:
        return Resolved(exact[0], [])
    prefix = [e for e in items if e.slug.startswith(wanted) or _slugish(e.name).startswith(wanted)]
    if len(prefix) == 1:
        return Resolved(prefix[0], [])
    if len(items) == 1:
        return Resolved(items[0], [])
    return Resolved(None, (prefix or items)[:MAX_CHOICES])
