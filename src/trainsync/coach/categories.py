"""Line categories of the savage pack (and of `config/messages.local.yaml`)."""

from enum import StrEnum


class Category(StrEnum):
    EXCUSE = "excuse"
    MISSED_WORKOUT = "missed_workout"
    UNDER_TARGET = "under_target"
    WORKOUT_START = "workout_start"
    REST_OVER = "rest_over"
    WORKOUT_DONE_GOOD = "workout_done_good"
    WORKOUT_DONE_BAD = "workout_done_bad"
    REMINDER_BEFORE = "reminder_before"
    REMINDER_NOW = "reminder_now"
    ESCALATION = "escalation"
    # Short English lines appended to about 1 in 4 savage messages; never sent alone.
    PUNCHLINE_EN = "punchline_en"


# Categories that are messages of their own (everything except the punchline add-on).
MESSAGE_CATEGORIES = tuple(c for c in Category if c is not Category.PUNCHLINE_EN)
