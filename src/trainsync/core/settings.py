"""Typed application settings, loaded from environment variables (and `.env`)."""

import base64
import binascii
from datetime import time
from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from trainsync.core.plate_inventory import DEFAULT_INVENTORY, parse_inventory

# The DEV-ONLY defaults in docker-compose.yml (`${VAR:-default}`) are labelled, so they are found by
# their label instead of by a copy of the values: plain ones start with `dev-`, and the dev Fernet
# key decodes to `dev-only-…`. Running with ENV=prod while one of them is still in use logs a
# warning at startup (tests/unit/core/test_dev_defaults.py checks every compose default is
# labelled).
DEV_ONLY_PREFIX = "dev-"
DEV_ONLY_SECRETS = (
    "STRAVA_CLIENT_SECRET",
    "STRAVA_WEBHOOK_VERIFY_TOKEN",
    "TOKEN_ENCRYPTION_KEY",
    "STATE_SIGNING_KEY",
    "API_KEYS",
    "SERVICE_API_KEYS",
)


def is_dev_default(value: str) -> bool:
    """A labelled dummy: `dev-…`, or a key whose base64 decodes to `dev-only…`."""
    if value.startswith(DEV_ONLY_PREFIX):
        return True
    try:
        return base64.urlsafe_b64decode(value.encode()).startswith(b"dev-only")
    except (binascii.Error, ValueError):
        return False


# Wording of every bot reply, notification and assistant prompt (ADR 0016).
BotTone = Literal["neutral", "hardcore"]
BotLang = Literal["en", "tr"]
# How hard the hardcore coach gets (ADR 0030): `savage` is an explicit opt-in.
BotIntensity = Literal["normal", "savage"]
# Where savage swears (ADR 0032): only in the roast lines, or in every savage message.
BotProfanity = Literal["roast", "max"]
RegistrationMode = Literal["invite", "open", "closed"]
# The emergency number in the distress reply (ADR 0032); 112 works across the EU and Türkiye.
DEFAULT_EMERGENCY_NUMBER = "112"


def parse_quiet_hours(value: str) -> tuple[time, time]:
    """`"23:00-07:00"` → (23:00, 07:00); an empty window ("00:00-00:00") means never quiet."""
    try:
        start, end = (time.fromisoformat(part.strip()) for part in value.split("-"))
    except ValueError as exc:
        raise ValueError(f"QUIET_HOURS must look like 23:00-07:00, got {value!r}") from exc
    return start, end


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    # Public read-only demo (P7.9, ADR 0028): every write answers 403;
    # `python -m trainsync.entrypoints.demo reset` (and the demo worker's nightly cron) refuse to
    # run unless this is on.
    demo_mode: bool = False

    database_url: str = "postgresql+asyncpg://trainsync:trainsync@localhost:5432/trainsync"
    redis_url: str = "redis://localhost:6379/0"

    strava_api_base_url: str = "https://www.strava.com/api/v3"
    strava_oauth_base_url: str = "https://www.strava.com/oauth"
    # Browser-facing OAuth base (the authorize redirect); defaults to STRAVA_OAUTH_BASE_URL.
    strava_oauth_public_base_url: str = ""
    strava_client_id: str
    strava_client_secret: SecretStr
    strava_redirect_uri: str = "http://localhost:8000/auth/strava/callback"
    strava_webhook_verify_token: SecretStr
    strava_webhook_subscription_id: int | None = None
    # Circuit breaker (per process): consecutive failed calls to open it, seconds until a probe.
    strava_breaker_failure_threshold: int = Field(default=5, ge=1)
    strava_breaker_cooldown_s: float = Field(default=30.0, gt=0)

    # The worker serves /metrics on this port (0 = off); the API serves it on its own port.
    worker_metrics_port: int = Field(default=9100, ge=0, le=65535)

    token_encryption_key: SecretStr
    state_signing_key: SecretStr
    api_keys: Annotated[list[SecretStr], NoDecode] = Field(min_length=1)

    @field_validator("api_keys", mode="before")
    @classmethod
    def _split_api_keys(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("strava_webhook_subscription_id", mode="before")
    @classmethod
    def _empty_as_none(cls, value: object) -> object:
        return None if value == "" else value

    def dev_secrets_in_use(self) -> list[str]:
        """Names (never values) of secrets still set to a docker-compose dev default."""
        current = {
            "STRAVA_CLIENT_SECRET": [self.strava_client_secret],
            "STRAVA_WEBHOOK_VERIFY_TOKEN": [self.strava_webhook_verify_token],
            # Every key of a rotation list decrypts, so a dev key anywhere in it is a problem.
            "TOKEN_ENCRYPTION_KEY": [
                SecretStr(k.strip())
                for k in self.token_encryption_key.get_secret_value().split(",")
            ],
            "STATE_SIGNING_KEY": [self.state_signing_key],
            "API_KEYS": self.api_keys,
            "SERVICE_API_KEYS": self.service_api_keys,
        }
        return [
            name
            for name, secrets in current.items()
            if any(is_dev_default(s.get_secret_value()) for s in secrets)
        ]

    @model_validator(mode="after")
    def _default_public_oauth_url(self) -> "Settings":
        if not self.strava_oauth_public_base_url:
            self.strava_oauth_public_base_url = self.strava_oauth_base_url
        return self

    # Phase 5 (web): browser URLs the OAuth callback may redirect back to after connecting
    # (`GET /auth/strava/login?return_to=`). Exact matches only; anything else is ignored.
    oauth_return_to_allowlist: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator("oauth_return_to_allowlist", mode="before")
    @classmethod
    def _split_return_to(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    # ---------------------------------------------------------------- accounts (P8.1, ADR 0034)
    # invite: an unused owner invite is needed; open: anyone may register; closed: nobody.
    registration_mode: RegistrationMode = "invite"
    # The owner account the single-user data migrates to (required when data exists).
    owner_email: str = ""
    session_ttl_days: int = Field(default=30, ge=1, le=365)
    session_max_age_days: int = Field(default=90, ge=1, le=730)
    # A session's expiry slides forward on use, written at most this often.
    session_touch_interval_s: int = Field(default=3600, ge=0, le=86400)
    invite_ttl_days: int = Field(default=7, ge=1, le=90)
    reset_ttl_minutes: int = Field(default=60, ge=5, le=1440)
    # Failed logins for one email inside the window lock it for the window (right password too).
    login_max_failures: int = Field(default=5, ge=1, le=100)
    login_lockout_minutes: int = Field(default=15, ge=1, le=1440)
    login_max_failures_per_ip: int = Field(default=20, ge=1, le=10000)
    register_max_per_hour: int = Field(default=5, ge=1, le=1000)
    # API keys that may act as any user with `X-Acting-User` (the bot's; ADR 0036). Every other
    # key of API_KEYS acts as the owner.
    service_api_keys: Annotated[list[SecretStr], NoDecode] = Field(default_factory=list)

    @field_validator("service_api_keys", mode="before")
    @classmethod
    def _split_service_keys(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("owner_email")
    @classmethod
    def _normal_owner_email(cls, value: str) -> str:
        return value.strip().lower()

    # ---------------------------------------------------------------- Telegram per user (P8.4)
    # `/link CODE`: the one-time code from the dashboard lives this long.
    telegram_link_code_ttl_minutes: int = Field(default=10, ge=1, le=60)
    # The bot's username (without @) for the dashboard's t.me deep link; empty = no link.
    telegram_bot_username: str = ""
    # The bot caches who a chat belongs to (and their settings) for this long.
    bot_chat_cache_s: int = Field(default=60, ge=0, le=3600)
    # Assistant questions per user per local day (the owner pays for the key; exempt).
    assistant_daily_limit: int = Field(default=50, ge=0, le=10000)
    # Fair sync (ADR 0037): a backfill job stops after this many pages and re-queues itself.
    backfill_pages_per_job: int = Field(default=10, ge=1, le=1000)

    # ---------------------------------------------------------------- bot + notifications (P5.5+)
    # All optional: the API and the worker start without them.
    # Empty token = the bot idles (metrics only) and notifications go nowhere (NullNotifier).
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_allowed_chat_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    # Chat that receives new-activity notifications; empty = the first allowlisted chat.
    telegram_notify_chat_id: int | None = None
    telegram_api_base_url: str = "https://api.telegram.org"
    # The read API the bot talks to (the bot never touches the DB) and its key;
    # an empty BOT_API_KEY falls back to the first of API_KEYS.
    bot_api_base_url: str = "http://localhost:8000"
    bot_api_key: SecretStr = SecretStr("")
    bot_metrics_port: int = Field(default=9101, ge=0, le=65535)
    # Base URL of the web dashboard; notifications link to `<url>/activities/<id>`. Empty = no link.
    dashboard_public_url: str = ""
    # Message pack for bot replies, notifications and the assistant prompt (ADR 0016).
    bot_tone: BotTone = "neutral"
    bot_lang: BotLang = "en"
    # Natural-language questions in the bot (P5.7, ADR 0014); off while the key is empty.
    anthropic_api_key: SecretStr = SecretStr("")
    assistant_model: str = "claude-sonnet-5-5"
    assistant_rate_limit_per_hour: int = Field(default=20, ge=1)

    @field_validator("telegram_allowed_chat_ids", mode="before")
    @classmethod
    def _split_chat_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("telegram_notify_chat_id", mode="before")
    @classmethod
    def _empty_chat_as_none(cls, value: object) -> object:
        return None if value == "" else value

    @property
    def bot_enabled(self) -> bool:
        return bool(self.telegram_bot_token.get_secret_value())

    @property
    def assistant_enabled(self) -> bool:
        return bool(self.anthropic_api_key.get_secret_value())

    def bot_read_api_key(self) -> SecretStr:
        """BOT_API_KEY, else the first service key (ADR 0036), else the first of API_KEYS."""
        if self.bot_api_key.get_secret_value():
            return self.bot_api_key
        return self.service_api_keys[0] if self.service_api_keys else self.api_keys[0]

    @property
    def all_api_keys(self) -> list[SecretStr]:
        """Every key the API accepts: the tooling keys and the service keys."""
        return [*self.api_keys, *self.service_api_keys]

    def notify_chat_id(self) -> int | None:
        if self.telegram_notify_chat_id is not None:
            return self.telegram_notify_chat_id
        return self.telegram_allowed_chat_ids[0] if self.telegram_allowed_chat_ids else None

    # ---------------------------------------------------------------- nutrition (P6.4, ADR 0019)
    # Open Food Facts lookup (public API, no key). Off = only the local food list is searched.
    openfoodfacts_enabled: bool = True
    openfoodfacts_base_url: str = "https://world.openfoodfacts.org"
    # OFF asks every client to identify itself: app name, version and a contact URL.
    openfoodfacts_user_agent: str = "trainsync/0.1 (+https://github.com/umutaydins/trainsync)"
    # Whole-request budget; on a timeout the endpoint answers with local results only.
    openfoodfacts_timeout_s: float = Field(default=3.0, gt=0, le=30)

    # ---------------------------------------------------------------- training (P6.3)
    # Plate calculator: bar weight and plates as `<kg>x<pairs>` (pairs = one plate per side).
    gym_bar_kg: Decimal = Field(default=Decimal(20), gt=0, le=100)
    gym_plates: Annotated[dict[Decimal, int], NoDecode] = Field(
        default_factory=lambda: dict(DEFAULT_INVENTORY)
    )
    # Double progression step when every set hit the top of the rep range (ADR 0018).
    progression_increment_kg: Decimal = Field(default=Decimal("2.5"), gt=0, le=20)
    progression_lower_body_increment_kg: Decimal = Field(default=Decimal(5), gt=0, le=20)

    @field_validator("gym_plates", mode="before")
    @classmethod
    def _parse_plates(cls, value: object) -> object:
        return parse_inventory(value) if isinstance(value, str) else value

    # ---------------------------------------------------------------- daily check-in (P6.9)
    # The evening "did you train?" prompt in Telegram (ADR 0020). Empty CHECKIN_ENABLED = on when a
    # bot token is set. CHECKIN_TZ is also the bot's "today" for /log, /eat, /kcal and /weight.
    checkin_enabled: bool | None = None
    checkin_time: time = time(21, 0)
    checkin_tz: str = "Europe/Istanbul"
    # One reminder this many minutes after the prompt when nothing was answered; 0 = none.
    checkin_reminder_minutes: int = Field(default=90, ge=0, le=720)

    @field_validator("checkin_enabled", mode="before")
    @classmethod
    def _empty_bool_as_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("checkin_tz")
    @classmethod
    def _known_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown time zone {value!r}") from exc
        return value

    @property
    def checkin_zone(self) -> ZoneInfo:
        return ZoneInfo(self.checkin_tz)

    @property
    def checkin_active(self) -> bool:
        """The scheduler sends prompts: a bot token, a target chat, and not switched off."""
        enabled = self.bot_enabled if self.checkin_enabled is None else self.checkin_enabled
        return enabled and self.bot_enabled and self.notify_chat_id() is not None

    # ---------------------------------------------------------------- stack alerts (P7.8)
    # The worker checks these every 5 minutes and sends one Telegram message when a condition
    # starts and one when it clears (ADR 0027). Off while no bot token and chat are set.
    # Strava circuit breaker not closed for this long.
    alert_circuit_open_minutes: int = Field(default=30, ge=1, le=1440)
    # Newest `trainsync-*.dump.age` in BACKUP_DIR older than this. Empty BACKUP_DIR = not checked
    # (compose.prod.yml mounts the backup folder read-only into the worker).
    alert_backup_max_age_hours: float = Field(default=36.0, gt=0, le=24 * 30)
    backup_dir: str = ""
    # No successful sync for this long while an athlete is connected.
    alert_sync_stale_hours: float = Field(default=2.0, gt=0, le=24 * 7)

    # ---------------------------------------------------------------- coach (P6.11, ADR 0030)
    # `savage` is the owner's explicit opt-in to an unrestricted, roasting coach (with
    # BOT_TONE=hardcore and BOT_LANG=tr); the guardrails hold in every intensity.
    bot_intensity: BotIntensity = "normal"
    # Timed coach messages (reminders, rest over, verdicts): on with a bot token and a chat.
    coach_messages_enabled: bool | None = None
    # Start time of a program day that has none of its own (local time, CHECKIN_TZ).
    workout_reminder_time: time = time(18, 0)
    # No proactive coach message in this local window ("HH:MM-HH:MM", may wrap midnight).
    quiet_hours: str = "23:00-07:00"
    # The owner's own extra lines, merged into the savage pack (git-ignored; optional).
    coach_messages_file: str = "config/messages.local.yaml"
    # Savage profanity (ADR 0032): `max` swears in every savage message; `/swear` per chat.
    bot_profanity: BotProfanity = "roast"
    # A day's free sugar (g) above this gets a savage food roast on the next /eat (ADR 0032).
    sugar_limit_g: float = Field(default=50.0, gt=0, le=1000)
    # One item above this sugar per 100 g gets a roast (the UK front-of-pack "high" mark).
    high_sugar_per_100g: float = Field(default=22.5, gt=0, le=100)
    # Named in the calm reply to distress talk (ADR 0032): digits, optionally a leading +.
    emergency_number: str = Field(default=DEFAULT_EMERGENCY_NUMBER, pattern=r"^\+?[0-9]{2,15}$")

    # ---- Progress statistics (P8.10, P8.11, ADR 0038)
    # Windows at least this long are cached in Redis, keyed by the user's data version.
    stats_cache_min_days: int = Field(default=180, ge=1, le=100000)
    stats_cache_ttl_s: int = Field(default=86400, ge=60, le=30 * 86400)
    # e1RM trend and PRs use sets of at most this many reps (Epley drifts above ~10).
    stats_e1rm_max_reps: int = Field(default=10, ge=1, le=30)
    # Weekly (Monday) and monthly (1st) digests; empty = on when TELEGRAM_BOT_TOKEN is set.
    stats_digest_enabled: bool | None = None
    # Local time of the digests (each user's zone; quiet hours postpone them).
    stats_digest_time: time = time(9, 0)

    @field_validator("coach_messages_enabled", "stats_digest_enabled", mode="before")
    @classmethod
    def _empty_coach_bool_as_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("quiet_hours")
    @classmethod
    def _valid_quiet_hours(cls, value: str) -> str:
        parse_quiet_hours(value)
        return value

    @property
    def quiet_window(self) -> tuple[time, time]:
        return parse_quiet_hours(self.quiet_hours)

    @property
    def coach_active(self) -> bool:
        """Timed coach messages go out: a bot token, a target chat, and not switched off."""
        enabled = (
            self.bot_enabled if self.coach_messages_enabled is None else self.coach_messages_enabled
        )
        return enabled and self.bot_enabled and self.notify_chat_id() is not None


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]  # required fields come from the environment
    except ValidationError as exc:
        # Fail fast with the variable names, not a pydantic traceback (and never the values).
        raise SystemExit(settings_error(exc)) from None


def settings_error(exc: ValidationError) -> str:
    """`trainsync: missing or invalid settings: TOKEN_ENCRYPTION_KEY (missing), ...`"""
    problems = []
    for error in exc.errors():
        name = "_".join(str(part) for part in error["loc"][:1]).upper() or "SETTINGS"
        reason = "missing" if error["type"] == "missing" else "invalid"
        problems.append(f"{name} ({reason})")
    return (
        "trainsync: missing or invalid settings: "
        + ", ".join(dict.fromkeys(problems))
        + ". Set them in the environment (production: .env.prod, see .env.prod.example)."
    )
