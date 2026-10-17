"""The only module that talks to Strava.

Every request goes through `_send`: explicit timeouts (shared client), retries with full jitter
on network errors / 5xx, rate-limit header parsing on every response, and 429 → `RateLimited`
without retrying (the calling job waits for the window reset).
"""

import random
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

import httpx
from pydantic import TypeAdapter

from trainsync.core.clock import Clock, Sleep, real_sleep, utc_now
from trainsync.core.logging import get_logger
from trainsync.core.settings import Settings
from trainsync.strava.budget import Priority
from trainsync.strava.errors import (
    RateLimited,
    StravaAuthError,
    StravaNotFound,
    StravaRequestError,
    StravaUnauthorized,
    StravaUnavailable,
)
from trainsync.strava.models import StravaActivity, StravaAthlete, TokenResponse
from trainsync.strava.ratelimit import RateLimitSnapshot, next_window_reset, parse_rate_limit
from trainsync.strava.retry import RetryPolicy, is_retryable

log = get_logger(__name__)

RateLimitCallback = Callable[[RateLimitSnapshot], Awaitable[None]]
QueryParams = Mapping[str, str | int]

_activities = TypeAdapter(list[StravaActivity])


class TokenProvider(Protocol):
    async def access_token(self, athlete_id: int) -> str: ...

    async def force_refresh(self, athlete_id: int) -> str: ...


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
        on_rate_limit: RateLimitCallback | None = None,
    ) -> None:
        self._http = http
        self._settings = settings
        self._tokens = token_provider
        self._policy = policy or RetryPolicy()
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or random.Random()  # noqa: S311  (jitter, not crypto)
        self._on_rate_limit = on_rate_limit

    def with_token_provider(self, token_provider: TokenProvider) -> "StravaClient":
        self._tokens = token_provider
        return self

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
        del priority  # consumed by the rate budget once it is wired in
        if self._tokens is None:
            raise RuntimeError("StravaClient has no token provider for API calls")
        url = f"{self._settings.strava_api_base_url}{path}"
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
                await self._sleep(self._policy.backoff(attempt, self._rng))
                continue

            self._log_call(template, response.status_code, started, attempt)
            await self._record_rate_limit(response)
            if response.is_success:
                return response
            if response.status_code == 429:
                raise RateLimited(reset_at=next_window_reset(self._clock()))
            if is_retryable(response):
                if attempt == last_attempt:
                    raise StravaUnavailable(f"{template}: {response.status_code}")
                await self._sleep(self._policy.backoff(attempt, self._rng))
                continue
            raise _client_error(response.status_code)
        raise AssertionError("unreachable")  # pragma: no cover

    async def _record_rate_limit(self, response: httpx.Response) -> None:
        snapshot = parse_rate_limit(response.headers)
        if snapshot is not None and self._on_rate_limit is not None:
            await self._on_rate_limit(snapshot)

    def _log_call(
        self,
        template: str,
        status: int | None,
        started: float,
        attempt: int,
        *,
        error: str | None = None,
    ) -> None:
        log.info(
            "strava_call",
            endpoint=template,
            status=status,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            attempt=attempt + 1,
            error=error,
        )


def _client_error(status_code: int) -> Exception:
    if status_code == 401:
        return StravaUnauthorized("strava rejected the access token")
    if status_code == 404:
        return StravaNotFound("strava object not found")
    return StravaRequestError(status_code)
