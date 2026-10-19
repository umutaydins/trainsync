"""`/v1/me/settings` bodies."""

from datetime import time
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from trainsync.core.settings import (
    BotIntensity,
    BotLang,
    BotProfanity,
    BotTone,
    parse_quiet_hours,
)
from trainsync.modules.users.settings import Effective

SETTINGS_EXAMPLE: dict[str, Any] = {
    "tone": "hardcore",
    "intensity": "normal",
    "profanity": "roast",
    "lang": "en",
    "checkin_enabled": True,
    "checkin_time": "21:00:00",
    "checkin_reminder_minutes": 90,
    "quiet_hours": "23:00-07:00",
    "workout_reminder_time": "18:00:00",
    "sugar_limit_g": 50.0,
    "country": "DE",
    "emergency_number": "112",
    "timezone": "Europe/Berlin",
    "custom": ["tone", "country"],
}

Country = Annotated[str, Field(pattern=r"^[A-Z]{2}$", examples=["DE"])]


class SettingsOut(BaseModel):
    """Effective values; `custom` names the ones the user set (the rest follow the defaults)."""

    model_config = ConfigDict(json_schema_extra={"examples": [SETTINGS_EXAMPLE]})

    tone: BotTone
    intensity: BotIntensity
    profanity: BotProfanity
    lang: BotLang
    checkin_enabled: bool
    checkin_time: time
    checkin_reminder_minutes: int
    quiet_hours: str
    workout_reminder_time: time
    sugar_limit_g: float
    country: str | None
    emergency_number: str = Field(description="From the country; EMERGENCY_NUMBER otherwise")
    timezone: str = Field(description="Change it with PATCH /v1/me")
    custom: list[str]

    @classmethod
    def build(cls, values: Effective, custom: list[str]) -> "SettingsOut":
        return cls(
            tone=values.tone,
            intensity=values.intensity,
            profanity=values.profanity,
            lang=values.lang,
            checkin_enabled=values.checkin_enabled,
            checkin_time=values.checkin_time,
            checkin_reminder_minutes=values.checkin_reminder_minutes,
            quiet_hours=values.quiet_hours,
            workout_reminder_time=values.workout_reminder_time,
            sugar_limit_g=values.sugar_limit_g,
            country=values.country,
            emergency_number=values.emergency_number,
            timezone=values.timezone,
            custom=custom,
        )


class SettingsPatch(BaseModel):
    """Only the fields sent change; `null` returns a field to the default."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"lang": "tr", "profanity": "max"}, {"country": None}]}
    )

    tone: BotTone | None = None
    intensity: BotIntensity | None = None
    profanity: BotProfanity | None = None
    lang: BotLang | None = None
    checkin_enabled: bool | None = None
    checkin_time: time | None = None
    checkin_reminder_minutes: Annotated[int, Field(ge=0, le=720)] | None = None
    quiet_hours: str | None = Field(default=None, examples=["22:30-06:30"])
    workout_reminder_time: time | None = None
    sugar_limit_g: Annotated[float, Field(gt=0, le=1000)] | None = None
    country: Country | None = None

    @field_validator("quiet_hours")
    @classmethod
    def _quiet(cls, value: str | None) -> str | None:
        if value is not None:
            parse_quiet_hours(value)
        return value


EXPORT_EXAMPLE: dict[str, Any] = {
    "version": 1,
    "exported_at": "2026-10-19T08:00:00+00:00",
    "account": {"id": 2, "email": "runner@example.com", "display_name": "Runner"},
    "tables": {"workouts": [{"id": 42, "started_at": "2026-10-18T17:00:00+00:00"}]},
}


class DeleteAccountIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"password": "correct horse"}]})

    password: Annotated[str, Field(min_length=1, max_length=128)]
