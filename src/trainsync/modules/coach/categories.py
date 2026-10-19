"""Line categories of the savage packs, one per language (and of `config/messages.local.yaml`)."""

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
    # The confirmation after /lang (ADR 0031).
    LANGUAGE_SET = "language_set"
    # ADR 0032: junk, sugar, alcohol, cigarettes, staying up late; the confirmation after /swear;
    # an unknown command.
    FOOD_ROAST = "food_roast"
    PROFANITY_SET = "profanity_set"
    UNKNOWN_COMMAND = "unknown_command"
    # Progress summaries and digests (P8.11): more work than the previous period, or less.
    PROGRESS_UP = "progress_up"
    PROGRESS_DOWN = "progress_down"
    # Short English lines appended to about 1 in 4 savage messages; never sent alone.
    PUNCHLINE_EN = "punchline_en"
    # Max profanity only (ADR 0032): a line put in front of every other savage message.
    MAX_OPENER = "max_opener"


# Categories with roast lines (every category except the max-only opener).
ROAST_CATEGORIES = tuple(c for c in Category if c is not Category.MAX_OPENER)
# Categories that are messages of their own (no punchline add-on, no max-only opener).
MESSAGE_CATEGORIES = tuple(c for c in ROAST_CATEGORIES if c is not Category.PUNCHLINE_EN)
