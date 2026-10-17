"""Typed views of the Strava JSON we use."""

from datetime import datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict


class StravaAthlete(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    firstname: str | None = None
    lastname: str | None = None


class StravaActivity(BaseModel):
    """An activity; unknown fields are kept so `raw()` returns the full JSON."""

    model_config = ConfigDict(extra="allow")

    id: int
    name: str
    sport_type: str
    start_date: AwareDatetime
    distance: float
    moving_time: int
    elapsed_time: int
    total_elevation_gain: float
    average_heartrate: float | None = None

    def raw(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token_type: str = "Bearer"  # noqa: S105  (a scheme name, not a secret)
    access_token: str
    refresh_token: str
    expires_at: datetime
    expires_in: int | None = None
    athlete: StravaAthlete | None = None

    def __repr__(self) -> str:
        return f"TokenResponse(expires_at={self.expires_at!r}, athlete={self.athlete!r})"

    __str__ = __repr__
