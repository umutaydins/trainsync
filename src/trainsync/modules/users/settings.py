"""Per-user settings (ADR 0036): stored overrides on top of the environment defaults.

A stored null means "the default", so changing `BOT_TONE` or `CHECKIN_TIME` reaches everyone
who never chose. `effective()` resolves one user's values; every consumer (bot, worker, API)
reads them through it.
"""

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from typing import cast
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.core.settings import (
    BotIntensity,
    BotLang,
    BotProfanity,
    BotTone,
    Settings,
    parse_quiet_hours,
)
from trainsync.modules.users.constants import EMERGENCY_NUMBERS
from trainsync.modules.users.models import UserSettings

# Columns a user may set (null resets to the default).
FIELDS = (
    "tone",
    "intensity",
    "profanity",
    "lang",
    "checkin_enabled",
    "stats_digest_enabled",
    "checkin_time",
    "checkin_reminder_minutes",
    "quiet_hours",
    "workout_reminder_time",
    "sugar_limit_g",
    "country",
)


@dataclass(frozen=True, slots=True)
class Effective:
    """One user's settings with every default applied."""

    user_id: int
    timezone: str
    tone: BotTone
    intensity: BotIntensity
    profanity: BotProfanity
    lang: BotLang
    checkin_enabled: bool
    stats_digest_enabled: bool
    checkin_time: time
    checkin_reminder_minutes: int
    quiet_hours: str
    workout_reminder_time: time
    sugar_limit_g: float
    country: str | None
    emergency_number: str

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def quiet_window(self) -> tuple[time, time]:
        return parse_quiet_hours(self.quiet_hours)

    @property
    def savage(self) -> bool:
        """Savage belongs to the hardcore tone (ADR 0030, 0031)."""
        return self.intensity == "savage" and self.tone == "hardcore"


def emergency_number(country: str | None, settings: Settings) -> str:
    return EMERGENCY_NUMBERS.get(country or "", settings.emergency_number)


def effective(
    user_id: int, timezone: str, row: UserSettings | None, settings: Settings
) -> Effective:
    def pick(name: str, default: object) -> object:
        value = getattr(row, name) if row is not None else None
        return default if value is None else value

    country = cast(str | None, pick("country", None))
    return Effective(
        user_id=user_id,
        timezone=timezone,
        tone=cast(BotTone, pick("tone", settings.bot_tone)),
        intensity=cast(BotIntensity, pick("intensity", settings.bot_intensity)),
        profanity=cast(BotProfanity, pick("profanity", settings.bot_profanity)),
        lang=cast(BotLang, pick("lang", settings.bot_lang)),
        checkin_enabled=bool(pick("checkin_enabled", settings.checkin_enabled is not False)),
        stats_digest_enabled=bool(
            pick("stats_digest_enabled", settings.stats_digest_enabled is not False)
        ),
        checkin_time=cast(time, pick("checkin_time", settings.checkin_time)),
        checkin_reminder_minutes=cast(
            int, pick("checkin_reminder_minutes", settings.checkin_reminder_minutes)
        ),
        quiet_hours=cast(str, pick("quiet_hours", settings.quiet_hours)),
        workout_reminder_time=cast(
            time, pick("workout_reminder_time", settings.workout_reminder_time)
        ),
        sugar_limit_g=float(cast(Decimal | float, pick("sugar_limit_g", settings.sugar_limit_g))),
        country=country,
        emergency_number=emergency_number(country, settings),
    )


class UserSettingsRepository:
    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    async def get(self) -> UserSettings | None:
        return await self._session.get(UserSettings, self._user_id)

    async def update(self, changes: dict[str, object], now: datetime) -> UserSettings:
        """Set the given columns (None resets one to its default); others are kept."""
        values = {name: changes[name] for name in FIELDS if name in changes}
        values["updated_at"] = now
        stmt = insert(UserSettings).values(user_id=self._user_id, **values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[UserSettings.user_id], set_={k: stmt.excluded[k] for k in values}
        )
        await self._session.execute(stmt)
        stored = await self._session.scalar(
            select(UserSettings)
            .where(UserSettings.user_id == self._user_id)
            .execution_options(populate_existing=True)
        )
        if stored is None:  # pragma: no cover - just upserted
            raise LookupError(self._user_id)
        return stored


async def effective_for(
    session: AsyncSession, settings: Settings, user_id: int, timezone: str
) -> Effective:
    row = await UserSettingsRepository(session, user_id).get()
    return effective(user_id, timezone, row, settings)
