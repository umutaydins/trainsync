"""OpenAPI examples of the progress statistics (one month of a runner who also lifts).

tests/unit/modules/stats/test_examples.py validates each against its model.
"""

from typing import Any

EXAMPLE_TZ = "Europe/Berlin"


def _change(value: float | None, previous: float | None) -> dict[str, float | None]:
    if value is None or previous is None:
        return {"value": value, "previous": previous, "change": None, "change_pct": None}
    diff = round(value - previous, 2)
    pct = round(diff / previous * 100, 1) if previous else None
    return {"value": value, "previous": previous, "change": diff, "change_pct": pct}


def _endurance(count: int, distance: float, moving: int, elevation: float) -> dict[str, Any]:
    return {
        "count": _change(count, count - 2),
        "distance_m": _change(distance, round(distance * 0.85)),
        "moving_time_s": _change(moving, round(moving * 0.9)),
        "elevation_gain_m": _change(elevation, round(elevation * 1.2)),
        "average_speed_mps": _change(round(distance / moving, 2), 2.95),
        "average_heartrate": _change(148.2, 151.0),
    }


WINDOW = {"from": "2026-10-01", "to": "2026-10-19", "days": 19}
PREVIOUS = {"from": "2026-09-01", "to": "2026-09-19", "days": 19}
EFFORT = {
    "group": "run",
    "activity_id": 812,
    "name": "Long run",
    "start_date": "2026-10-12T07:02:11Z",
    "distance_m": 21300.0,
    "moving_time_s": 6840,
    "average_speed_mps": 3.11,
}

PROGRESS_EXAMPLE: dict[str, Any] = {
    "period": "month",
    "timezone": EXAMPLE_TZ,
    "window": WINDOW,
    "previous": PREVIOUS,
    "endurance": {
        "totals": _endurance(11, 98400.0, 31200, 640.0),
        "by_group": [{"group": "run", **_endurance(9, 86400.0, 27600, 560.0)}],
        "longest": [EFFORT],
        "fastest": [{**EFFORT, "activity_id": 805, "name": "Tempo 5k", "distance_m": 5020.0}],
    },
    "strength": {
        "sessions": _change(6, 5),
        "sets": _change(102, 88),
        "reps": _change(744, 690),
        "tonnage_kg": _change(41250.0, 37800.0),
        "pr_count": _change(3, 1),
        "by_muscle": [{"muscle": "chest", "sets": 24, "tonnage_kg": 11400.0}],
        "by_exercise": [
            {
                "exercise_id": 1,
                "name": "Bench Press",
                "muscle": "chest",
                "sets": 15,
                "reps": 90,
                "tonnage_kg": 7650.0,
                "best_e1rm_kg": _change(101.67, 98.0),
            }
        ],
        "adherence": {
            "program_id": 3,
            "program_name": "Upper/Lower 4-day",
            "planned_sessions": 8,
            "done_sessions": 6,
            "planned_sets": 136,
            "done_sets": 102,
            "session_ratio": 0.75,
            "set_ratio": 0.75,
        },
    },
    "consistency": {
        "active_days": _change(14, 12),
        "training_streak_weeks": 9,
        "longest_training_streak_weeks": 15,
        "checkin_streak_days": 6,
        "longest_checkin_streak_days": 41,
        "checkin_rate": _change(0.89, 0.79),
    },
    "nutrition": {
        "logged_days": _change(17, 15),
        "logging_rate": _change(0.89, 0.79),
        "avg_kcal": _change(2480.0, 2610.0),
        "kcal_target": 2500,
        "avg_protein_g": _change(152.0, 139.0),
        "avg_carbs_g": _change(270.0, 301.0),
        "avg_fat_g": _change(81.0, 86.0),
        "days_over_sugar_limit": _change(2, 5),
        "sugar_limit_g": 50.0,
    },
    "body": {
        "first_kg": 81.4,
        "last_kg": 80.6,
        "change_kg": _change(-0.8, -0.3),
        "moving_average_kg": 80.8,
        "rate_kg_per_week": _change(-0.31, -0.12),
        "body_fat_pct": None,
    },
}

SERIES_EXAMPLE: dict[str, Any] = {
    "metric": "kcal",
    "period": "week",
    "bucket": "day",
    "timezone": EXAMPLE_TZ,
    "window": {"from": "2026-10-19", "to": "2026-10-19", "days": 1},
    "sport": None,
    "target": 2500.0,
    "points": [{"start": "2026-10-19", "value": 2310.5, "moving_average": None}],
}

HEATMAP_EXAMPLE: dict[str, Any] = {
    "year": 2026,
    "timezone": EXAMPLE_TZ,
    "max_value": 182.0,
    "days": [
        {"day": "2026-01-01", "value": 0.0, "sessions": 0, "checkin": None},
        {"day": "2026-01-02", "value": 64.5, "sessions": 1, "checkin": "done"},
    ],
}

PRS_EXAMPLE: dict[str, Any] = {
    "period": "all",
    "window": {"from": "2024-03-02", "to": "2026-10-19", "days": 962},
    "count": 1,
    "records": [
        {
            "exercise_id": 1,
            "name": "Bench Press",
            "workout_id": 418,
            "achieved_at": "2026-10-16T17:40:02Z",
            "e1rm_kg": 101.67,
            "previous_kg": 100.0,
        }
    ],
}
