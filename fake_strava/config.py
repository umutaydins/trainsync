"""Runtime configuration for fake_strava (env prefix `FAKE_STRAVA_`)."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FakeStravaConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FAKE_STRAVA_", extra="ignore")

    latency_ms: int = Field(default=0, ge=0)
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    rate_limit_15min: int = Field(default=200, ge=0)
    rate_limit_daily: int = Field(default=2000, ge=0)
    # Read-specific limits; `None` means "same as the overall limits".
    read_rate_limit_15min: int | None = Field(default=None, ge=0)
    read_rate_limit_daily: int | None = Field(default=None, ge=0)
    token_ttl_s: int = Field(default=21600, ge=0)
    seed_activities: int = Field(default=300, ge=0)
    rng_seed: int = 42
    athletes: int = Field(default=1, ge=1)
    # `subscription_id` in the webhook events the fake sends (trainsync checks it when set).
    webhook_subscription_id: int = 1
    # When set, /oauth/token checks them; when unset any client is accepted.
    client_id: str | None = None
    client_secret: str | None = None

    @property
    def read_limit_15min(self) -> int:
        if self.read_rate_limit_15min is None:
            return self.rate_limit_15min
        return self.read_rate_limit_15min

    @property
    def read_limit_daily(self) -> int:
        if self.read_rate_limit_daily is None:
            return self.rate_limit_daily
        return self.read_rate_limit_daily
