"""Typed application settings, loaded from environment variables (and `.env`)."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # required fields come from the environment
