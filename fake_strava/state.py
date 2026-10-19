"""In-memory state of fake_strava: athletes, activities, tokens, rate-limit counters, stats.

Everything runs on one event loop and no method awaits, so no locking is needed.
"""

import random
import secrets
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fake_strava.clock import Clock
from fake_strava.config import FakeStravaConfig
from fake_strava.seed import (
    FakeActivity,
    FakeAthlete,
    first_activity_id,
    seed_activities,
    seed_athletes,
)

ActivityAction = Literal["create", "update", "delete"]


@dataclass
class AccessToken:
    athlete_id: int
    expires_at: datetime


@dataclass
class AuthCode:
    athlete_id: int
    scope: str


@dataclass
class TokenGrant:
    access_token: str
    refresh_token: str
    expires_at: datetime
    athlete: FakeAthlete

    def to_json(self, *, with_athlete: bool, ttl_s: int) -> dict[str, Any]:
        data: dict[str, Any] = {
            "token_type": "Bearer",
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": int(self.expires_at.timestamp()),
            "expires_in": ttl_s,
        }
        if with_athlete:
            data["athlete"] = self.athlete.to_json()
        return data


@dataclass
class RateLimitCounter:
    window_start: datetime | None = None
    day: str | None = None
    short: int = 0
    daily: int = 0


@dataclass
class ActivityChange:
    """An athlete-side edit. P3.2 turns these into webhook events."""

    action: ActivityAction
    activity_id: int
    athlete_id: int
    at: datetime


@dataclass
class RateLimitDecision:
    allowed: bool
    headers: dict[str, str] = field(default_factory=dict)


class OAuthError(Exception):
    def __init__(self, field_name: str) -> None:
        super().__init__(field_name)
        self.field_name = field_name


def window_start(now: datetime) -> datetime:
    now = now.astimezone(UTC)
    return now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)


class FakeStravaState:
    def __init__(self, config: FakeStravaConfig, clock: Clock) -> None:
        self.config = config
        self.clock = clock
        self.reset()

    # ------------------------------------------------------------------ lifecycle
    def reset(self) -> None:
        cfg = self.config
        self.rng = random.Random(f"errors:{cfg.rng_seed}")
        self.webhook_rng = random.Random(f"webhooks:{cfg.rng_seed}")
        self.athletes: dict[int, FakeAthlete] = {
            a.id: a for a in seed_athletes(cfg.athletes, cfg.rng_seed)
        }
        self.activities: dict[int, FakeActivity] = {}
        seed_end = self.clock.now()
        for index, athlete_id in enumerate(self.athletes):
            for activity in seed_activities(
                athlete_id, cfg.seed_activities, cfg.rng_seed, seed_end, first_activity_id(index)
            ):
                self.activities[activity.id] = activity
        self.codes: dict[str, AuthCode] = {}
        self.access_tokens: dict[str, AccessToken] = {}
        self.refresh_tokens: dict[str, int] = {}
        # Athletes that deauthorized the app through `POST /oauth/deauthorize`, in order.
        self.deauthorized: list[int] = []
        self.overall = RateLimitCounter()
        self.read = RateLimitCounter()
        self.stats: Counter[tuple[str, int]] = Counter()
        self.changes: list[ActivityChange] = []

    @property
    def default_athlete_id(self) -> int:
        return next(iter(self.athletes))

    def update_config(self, changes: dict[str, Any]) -> FakeStravaConfig:
        merged = self.config.model_dump() | changes
        self.config = FakeStravaConfig.model_validate(merged)
        return self.config

    # ------------------------------------------------------------------ oauth
    def issue_code(self, athlete_id: int, scope: str) -> str:
        if athlete_id not in self.athletes:
            raise OAuthError("athlete_id")
        code = secrets.token_hex(16)
        self.codes[code] = AuthCode(athlete_id=athlete_id, scope=scope)
        return code

    def check_client(self, client_id: str | None, client_secret: str | None) -> None:
        if self.config.client_id is not None and client_id != self.config.client_id:
            raise OAuthError("client_id")
        if self.config.client_secret is not None and client_secret != self.config.client_secret:
            raise OAuthError("client_secret")

    def exchange_code(self, code: str) -> TokenGrant:
        auth = self.codes.pop(code, None)
        if auth is None:
            raise OAuthError("code")
        return self._grant(auth.athlete_id)

    def refresh(self, refresh_token: str) -> TokenGrant:
        """Always rotates: the old refresh token stops working."""
        athlete_id = self.refresh_tokens.pop(refresh_token, None)
        if athlete_id is None:
            raise OAuthError("refresh_token")
        return self._grant(athlete_id)

    def _grant(self, athlete_id: int) -> TokenGrant:
        access, refresh = secrets.token_hex(20), secrets.token_hex(20)
        expires_at = self.clock.now().replace(microsecond=0) + timedelta(
            seconds=self.config.token_ttl_s
        )
        self.access_tokens[access] = AccessToken(athlete_id=athlete_id, expires_at=expires_at)
        self.refresh_tokens[refresh] = athlete_id
        return TokenGrant(access, refresh, expires_at, self.athletes[athlete_id])

    def authenticate(self, access_token: str) -> int | None:
        token = self.access_tokens.get(access_token)
        if token is None or token.expires_at <= self.clock.now():
            return None
        return token.athlete_id

    def expire_tokens(self, athlete_id: int | None = None) -> int:
        expired_at = self.clock.now() - timedelta(seconds=1)
        count = 0
        for token in self.access_tokens.values():
            if athlete_id is None or token.athlete_id == athlete_id:
                token.expires_at = expired_at
                count += 1
        return count

    def revoke(self, athlete_id: int) -> int:
        """The athlete revoked our access: all their tokens stop working."""
        access = [t for t, a in self.access_tokens.items() if a.athlete_id == athlete_id]
        refresh = [t for t, a in self.refresh_tokens.items() if a == athlete_id]
        for token in access:
            del self.access_tokens[token]
        for token in refresh:
            del self.refresh_tokens[token]
        return len(access)

    # ------------------------------------------------------------------ rate limits
    def consume_rate_limit(self) -> RateLimitDecision:
        """Count one request against the budget unless it is already exhausted."""
        now = self.clock.now()
        cfg = self.config
        for counter in (self.overall, self.read):
            _roll(counter, now)
        allowed = (
            self.overall.short < cfg.rate_limit_15min
            and self.overall.daily < cfg.rate_limit_daily
            and self.read.short < cfg.read_limit_15min
            and self.read.daily < cfg.read_limit_daily
        )
        if allowed:
            for counter in (self.overall, self.read):
                counter.short += 1
                counter.daily += 1
        return RateLimitDecision(allowed=allowed, headers=self.rate_limit_headers())

    def rate_limit_headers(self) -> dict[str, str]:
        cfg = self.config
        return {
            "X-RateLimit-Limit": f"{cfg.rate_limit_15min},{cfg.rate_limit_daily}",
            "X-RateLimit-Usage": f"{self.overall.short},{self.overall.daily}",
            "X-ReadRateLimit-Limit": f"{cfg.read_limit_15min},{cfg.read_limit_daily}",
            "X-ReadRateLimit-Usage": f"{self.read.short},{self.read.daily}",
        }

    def injected_error(self) -> int | None:
        if self.config.error_rate > 0 and self.rng.random() < self.config.error_rate:
            return self.rng.choice([500, 502, 503])
        return None

    # ------------------------------------------------------------------ activities
    def list_activities(
        self,
        athlete_id: int,
        *,
        before: int | None,
        after: int | None,
        page: int,
        per_page: int,
    ) -> list[FakeActivity]:
        items = [
            a
            for a in self.activities.values()
            if a.athlete_id == athlete_id
            and (before is None or a.start_date.timestamp() < before)
            and (after is None or a.start_date.timestamp() > after)
        ]
        items.sort(key=lambda a: (a.start_date, a.id), reverse=True)
        offset = (page - 1) * per_page
        return items[offset : offset + per_page]

    def get_activity(self, athlete_id: int, activity_id: int) -> FakeActivity | None:
        activity = self.activities.get(activity_id)
        if activity is None or activity.athlete_id != athlete_id:
            return None
        return activity

    def apply_change(
        self,
        action: ActivityAction,
        *,
        athlete_id: int | None,
        activity_id: int | None,
        fields: dict[str, Any],
    ) -> FakeActivity | None:
        """Simulate the athlete creating, editing or deleting an activity."""
        owner = athlete_id or self.default_athlete_id
        if owner not in self.athletes:
            raise KeyError("athlete")
        if action == "create":
            activity = self._create(owner, activity_id, fields)
        else:
            if activity_id is None or activity_id not in self.activities:
                raise KeyError("activity")
            activity = self.activities[activity_id]
            owner = activity.athlete_id
            if action == "update":
                _apply_fields(activity, fields)
            else:
                del self.activities[activity_id]
        self.changes.append(ActivityChange(action, activity.id, owner, self.clock.now()))
        return None if action == "delete" else activity

    def _create(
        self, athlete_id: int, activity_id: int | None, fields: dict[str, Any]
    ) -> FakeActivity:
        new_id = activity_id or max(self.activities, default=first_activity_id(0) - 1) + 1
        if new_id in self.activities:
            raise ValueError("activity id already exists")
        activity = FakeActivity(
            id=new_id,
            athlete_id=athlete_id,
            name="New Activity",
            sport_type="Run",
            start_date=self.clock.now().replace(microsecond=0),
            distance=5000.0,
            moving_time=1500,
            elapsed_time=1600,
            total_elevation_gain=20.0,
        )
        _apply_fields(activity, fields)
        self.activities[new_id] = activity
        return activity

    # ------------------------------------------------------------------ stats
    def record(self, endpoint: str, status: int) -> None:
        self.stats[(endpoint, status)] += 1

    def stats_json(self) -> dict[str, Any]:
        by_endpoint: dict[str, dict[str, int]] = {}
        for (endpoint, status), count in sorted(self.stats.items()):
            by_endpoint.setdefault(endpoint, {})[str(status)] = count
        return {
            "total": sum(self.stats.values()),
            "requests": by_endpoint,
            "rate_limit": {
                "short_usage": self.overall.short,
                "daily_usage": self.overall.daily,
            },
        }


_EDITABLE = {
    "name",
    "sport_type",
    "distance",
    "moving_time",
    "elapsed_time",
    "total_elevation_gain",
    "average_heartrate",
}


def _apply_fields(activity: FakeActivity, fields: dict[str, Any]) -> None:
    for key, value in fields.items():
        if key == "start_date":
            activity.start_date = _parse_ts(value)
        elif key in _EDITABLE:
            setattr(activity, key, value)
        else:
            raise ValueError(f"unknown activity field: {key}")


def _parse_ts(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("start_date must be an ISO-8601 string")
    if parsed.tzinfo is None:
        raise ValueError("start_date must include a timezone")
    return parsed.astimezone(UTC)


def _roll(counter: RateLimitCounter, now: datetime) -> None:
    start = window_start(now)
    day = now.astimezone(UTC).date().isoformat()
    if counter.window_start != start:
        counter.window_start, counter.short = start, 0
    if counter.day != day:
        counter.day, counter.daily = day, 0
