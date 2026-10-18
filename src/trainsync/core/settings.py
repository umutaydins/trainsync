"""Typed application settings, loaded from environment variables (and `.env`)."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Wording of every bot reply, notification and assistant prompt (ADR 0016).
BotTone = Literal["neutral", "hardcore"]
BotLang = Literal["en", "tr"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

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
        return self.bot_api_key if self.bot_api_key.get_secret_value() else self.api_keys[0]

    def notify_chat_id(self) -> int | None:
        if self.telegram_notify_chat_id is not None:
            return self.telegram_notify_chat_id
        return self.telegram_allowed_chat_ids[0] if self.telegram_allowed_chat_ids else None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # required fields come from the environment
