"""The only module that talks to Strava.

Every request goes through `_send`: explicit timeouts (shared client), retries with full jitter
on network errors / 5xx, rate-limit header parsing on every response, and 429 → `RateLimited`
without retrying (the calling job waits for the window reset). Every API call also passes the
per-process circuit breaker, which fails fast with `CircuitOpen` while Strava is down.
"""

import random
import time
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Protocol

import httpx
from pydantic import TypeAdapter

from trainsync.core.clock import Clock, Sleep, real_sleep, utc_now
from trainsync.core.logging import get_logger
from trainsync.core.metrics import STRAVA_REQUEST_DURATION, STRAVA_REQUESTS, STRAVA_RETRIES
from trainsync.core.settings import Settings
from trainsync.strava.breaker import BreakerListener, BreakerState, CircuitBreaker
from trainsync.strava.budget import Allowance, Priority
from trainsync.strava.errors import (
    RateLimited,
    StravaAuthError,
    StravaNotFound,
    StravaRequestError,
    StravaUnauthorized,
    StravaUnavailable,
)
from trainsync.strava.models import (
    PushSubscription,
    StravaActivity,
    StravaAthlete,
    TokenResponse,
)
from trainsync.strava.ratelimit import (
    RateLimitSnapshot,
    next_daily_reset,
    next_window_reset,
    parse_rate_limit,
)
from trainsync.strava.retry import RetryPolicy, is_retryable

log = get_logger(__name__)

QueryParams = Mapping[str, str | int]

_activities = TypeAdapter(list[StravaActivity])
_subscriptions = TypeAdapter(list[PushSubscription])


class TokenProvider(Protocol):
    async def access_token(self, athlete_id: int) -> str: ...

    async def force_refresh(self, athlete_id: int) -> str: ...


class RateLimitHook(Protocol):
    """What the client needs from the rate budget (implemented by `RateBudget`)."""

    async def allow(self, priority: Priority) -> Allowance: ...

    async def record(self, snapshot: RateLimitSnapshot) -> None: ...

    async def block_until(self, reset_at: datetime) -> None: ...


class StravaClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        settings: Settings,
        token_provider: TokenProvider | None = None,
        *,
        policy: RetryPolicy | None = None,
        clock: Clock = utc_now,
        sleep: Sleep = real_sleep,
        rng: random.Random | None = None,
        budget: RateLimitHook | None = None,
        breaker: CircuitBreaker | None = None,
        breaker_listener: BreakerListener | None = None,
    ) -> None:
        self._http = http
        self._settings = settings
        self._tokens = token_provider
        self._policy = policy or RetryPolicy()
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or random.Random()  # noqa: S311  (jitter, not crypto)
        self._budget = budget
        self._breaker = breaker or CircuitBreaker(
            settings.strava_breaker_failure_threshold,
            timedelta(seconds=settings.strava_breaker_cooldown_s),
            clock,
            breaker_listener,
        )

    def with_token_provider(self, token_provider: TokenProvider) -> "StravaClient":
        self._tokens = token_provider
        return self

    @property
    def breaker_state(self) -> BreakerState:
        return self._breaker.state

    # ------------------------------------------------------------------ API

    async def get_athlete(self, athlete_id: int, *, priority: Priority = "low") -> StravaAthlete:
        response = await self._api("GET", "/athlete", "/athlete", athlete_id, priority=priority)
        return StravaAthlete.model_validate(response.json())

    async def list_activities(
        self,
        athlete_id: int,
        *,
        before: int | None = None,
        after: int | None = None,
        page: int = 1,
        per_page: int = 200,
        priority: Priority = "low",
    ) -> list[StravaActivity]:
        params: dict[str, str | int] = {"page": page, "per_page": per_page}
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after
        response = await self._api(
            "GET",
            "/athlete/activities",
            "/athlete/activities",
            athlete_id,
            params=params,
            priority=priority,
        )
        return _activities.validate_python(response.json())

    async def get_activity(
        self, athlete_id: int, activity_id: int, *, priority: Priority = "low"
    ) -> StravaActivity:
        response = await self._api(
            "GET", "/activities/{id}", f"/activities/{activity_id}", athlete_id, priority=priority
        )
        return StravaActivity.model_validate(response.json())

    # ---------------------------------------------------------------- OAuth

    async def exchange_code(self, code: str) -> TokenResponse:
        return await self._token_request({"grant_type": "authorization_code", "code": code})

    async def refresh(self, refresh_token: str) -> TokenResponse:
        return await self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )

    async def _token_request(self, fields: dict[str, str]) -> TokenResponse:
        data = {
            "client_id": self._settings.strava_client_id,
            "client_secret": self._settings.strava_client_secret.get_secret_value(),
            **fields,
        }
        url = f"{self._settings.strava_oauth_base_url}/token"
        try:
            response = await self._send("POST", "/oauth/token", url, data=data)
        except (StravaRequestError, StravaNotFound) as exc:
            raise StravaAuthError("strava rejected the token request") from exc
        return TokenResponse.model_validate(response.json())

    # ------------------------------------------------- webhook subscription (P7.7)
    # App-level calls: authenticated with the client id and secret, not an athlete token.

    async def create_push_subscription(
        self, callback_url: str, verify_token: str
    ) -> PushSubscription:
        """Strava verifies `callback_url` with a GET (hub.challenge) before answering."""
        data = {
            **self._app_credentials(),
            "callback_url": callback_url,
            "verify_token": verify_token,
        }
        url = f"{self._settings.strava_api_base_url}/push_subscriptions"
        response = await self._send("POST", "/push_subscriptions", url, data=data)
        return PushSubscription.model_validate(response.json())

    async def list_push_subscriptions(self) -> list[PushSubscription]:
        url = f"{self._settings.strava_api_base_url}/push_subscriptions"
        response = await self._send(
            "GET", "/push_subscriptions", url, params=self._app_credentials()
        )
        return _subscriptions.validate_python(response.json())

    async def delete_push_subscription(self, subscription_id: int) -> None:
        url = f"{self._settings.strava_api_base_url}/push_subscriptions/{subscription_id}"
        template = "/push_subscriptions/{id}"
        await self._send("DELETE", template, url, params=self._app_credentials())

    def _app_credentials(self) -> dict[str, str]:
        return {
            "client_id": self._settings.strava_client_id,
            "client_secret": self._settings.strava_client_secret.get_secret_value(),
        }

    # ------------------------------------------------------------- plumbing

    async def _api(
        self,
        method: str,
        template: str,
        path: str,
        athlete_id: int,
        *,
        params: QueryParams | None = None,
        priority: Priority,
    ) -> httpx.Response:
        if self._tokens is None:
            raise RuntimeError("StravaClient has no token provider for API calls")
        if self._budget is not None:
            allowance = await self._budget.allow(priority)
            if not allowance.allowed:
                raise RateLimited(reset_at=allowance.resume_at or next_window_reset(self._clock()))
        url = f"{self._settings.strava_api_base_url}{path}"
        # After the budget check, so a budget denial is never mistaken for an answer from Strava.
        async with self._breaker.guard():
            token = await self._tokens.access_token(athlete_id)
            try:
                return await self._send(method, template, url, params=params, token=token)
            except StravaUnauthorized:
                # Refresh once and retry once; a second 401 means access was revoked.
                token = await self._tokens.force_refresh(athlete_id)
                try:
                    return await self._send(method, template, url, params=params, token=token)
                except StravaUnauthorized as exc:
                    raise StravaAuthError("strava rejected a freshly refreshed token") from exc
        raise AssertionError("unreachable")  # pragma: no cover

    async def _send(
        self,
        method: str,
        template: str,
        url: str,
        *,
        params: QueryParams | None = None,
        data: Mapping[str, str] | None = None,
        token: str | None = None,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token is not None else None
        last_attempt = self._policy.max_attempts - 1
        for attempt in range(self._policy.max_attempts):
            started = time.perf_counter()
            try:
                response = await self._http.request(
                    method, url, params=params, data=data, headers=headers
                )
            except httpx.TransportError as exc:
                self._log_call(template, None, started, attempt, error=type(exc).__name__)
                if attempt == last_attempt:
                    raise StravaUnavailable(f"{template}: {type(exc).__name__}") from exc
                STRAVA_RETRIES.inc()
                await self._sleep(self._policy.backoff(attempt, self._rng))
                continue

            self._log_call(template, response.status_code, started, attempt)
            snapshot = await self._record_rate_limit(response)
            if response.is_success:
                return response
            if response.status_code == 429:
                reset_at = self._reset_after_429(snapshot)
                if self._budget is not None:
                    await self._budget.block_until(reset_at)
                raise RateLimited(reset_at=reset_at)
            if is_retryable(response):
                if attempt == last_attempt:
                    raise StravaUnavailable(f"{template}: {response.status_code}")
                STRAVA_RETRIES.inc()
                await self._sleep(self._policy.backoff(attempt, self._rng))
                continue
            raise _client_error(response.status_code)
        raise AssertionError("unreachable")  # pragma: no cover

    async def _record_rate_limit(self, response: httpx.Response) -> RateLimitSnapshot | None:
        snapshot = parse_rate_limit(response.headers)
        if snapshot is not None and self._budget is not None:
            await self._budget.record(snapshot)
        return snapshot

    def _reset_after_429(self, snapshot: RateLimitSnapshot | None) -> datetime:
        """The daily budget resets at midnight UTC, the 15-minute one on the quarter hour."""
        now = self._clock()
        if snapshot is not None and snapshot.daily_ratio >= 1.0:
            return next_daily_reset(now)
        return next_window_reset(now)

    def _log_call(
        self,
        template: str,
        status: int | None,
        started: float,
        attempt: int,
        *,
        error: str | None = None,
    ) -> None:
        duration = time.perf_counter() - started
        STRAVA_REQUESTS.labels(template, "error" if status is None else str(status)).inc()
        STRAVA_REQUEST_DURATION.labels(template).observe(duration)
        log.info(
            "strava_call",
            endpoint=template,
            status=status,
            duration_ms=round(duration * 1000, 1),
            attempt=attempt + 1,
            error=error,
        )


def _client_error(status_code: int) -> Exception:
    if status_code == 401:
        return StravaUnauthorized("strava rejected the access token")
    if status_code == 404:
        return StravaNotFound("strava object not found")
    return StravaRequestError(status_code)
