"""The four read-API tools the assistant may call, as Messages API tool definitions."""

from anthropic.types.beta import BetaToolParam

MAX_LIST_LIMIT = 50


def _nullable(kind: str, description: str) -> dict[str, object]:
    return {"type": [kind, "null"], "description": description}


_DATE = {"type": "string", "description": "UTC day, YYYY-MM-DD"}


_SPORT = _nullable("string", "Strava sport_type such as Run, Ride, Swim; null for all sports")


_RANGE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "from": {**_DATE, "description": "First day, YYYY-MM-DD (inclusive)"},
        "to": {**_DATE, "description": "Last day, YYYY-MM-DD (inclusive)"},
        "sport_type": _SPORT,
    },
    "required": ["from", "to", "sport_type"],
    "additionalProperties": False,
}


TOOLS: list[BetaToolParam] = [
    {
        "name": "get_summary",
        "description": (
            "Totals for a date range: count, distance_m, moving_time_s, elevation_gain_m, the "
            "same per sport_type, and the longest activity. Use for 'how much / how far / how "
            "many' questions over a period."
        ),
        "input_schema": _RANGE_SCHEMA,
        "strict": True,
    },
    {
        "name": "get_weekly",
        "description": (
            "Per ISO week (Monday start) totals for a date range, zero-filled. Use for trends, "
            "best or worst week, week-by-week comparisons."
        ),
        "input_schema": _RANGE_SCHEMA,
        "strict": True,
    },
    {
        "name": "list_activities",
        "description": (
            "Individual activities, newest first: name, sport_type, start_date, distance_m, "
            "moving_time_s, elevation_gain_m, average_heartrate. Use for questions about "
            "specific workouts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "from": _nullable("string", "First day, YYYY-MM-DD, or null"),
                "to": _nullable("string", "Day after the last one, YYYY-MM-DD, or null"),
                "sport_type": _SPORT,
                "limit": {"type": "integer", "description": f"1 to {MAX_LIST_LIMIT}"},
            },
            "required": ["from", "to", "sport_type", "limit"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "get_sync_status",
        "description": "How fresh the data is and whether syncing with Strava is healthy.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "strict": True,
    },
]
