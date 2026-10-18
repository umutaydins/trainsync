"""A small Telegram Bot API client on the shared httpx client (ADR 0013).

Only the two methods we use: `getUpdates` (long polling) and `sendMessage`. The bot token is part
of every URL, so neither URLs nor httpx exceptions (which carry the URL) are ever logged or put
into our own exception messages.

Retries: a 429 waits exactly `parameters.retry_after` seconds; 5xx and network errors back off
exponentially (1, 2, 4, … s, capped). Waiting goes through the injected `sleep`.
"""

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from trainsync.core.clock import Sleep, real_sleep
from trainsync.core.logging import get_logger

log = get_logger(__name__)

# Long polling: Telegram holds `getUpdates` open for up to `timeout` s; the read timeout of the
# HTTP request must be longer than that.
POLL_TIMEOUT_S = 25
BACKOFF_BASE_S = 1.0
BACKOFF_MAX_S = 30.0
# Telegram's hard limit for one message.
MAX_MESSAGE_LEN = 4096


class TelegramError(Exception):
    """Telegram answered with a non-retryable error (e.g. 400 chat not found, 401 bad token)."""

    def __init__(self, status: int, description: str) -> None:
        super().__init__(f"telegram error {status}: {description}")
        self.status = status


class TelegramRetryAfterError(Exception):
    """429: Telegram asked us to wait `retry_after` seconds (raised once attempts run out)."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"telegram flood control, retry after {retry_after:g} s")
        self.retry_after = retry_after


class TelegramUnavailableError(Exception):
    """5xx or a network error before the request was sent: the message was not delivered."""


class TelegramDeliveryUnknownError(TelegramUnavailableError):
    """The request was sent but no answer came back (read timeout, dropped connection):
    the message may or may not have been delivered."""


class Chat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message_id: int
    chat: Chat
    text: str | None = None


class Update(BaseModel):
    model_config = ConfigDict(extra="ignore")

    update_id: int
    message: Message | None = None


class _Envelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ok: bool
    result: Any = None
    error_code: int | None = None
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


def backoff_delay(attempt: int) -> float:
    """1, 2, 4, … seconds for attempt 1, 2, 3, …, capped at `BACKOFF_MAX_S`."""
    return float(min(BACKOFF_BASE_S * 2 ** (attempt - 1), BACKOFF_MAX_S))


class TelegramApi:
    def __init__(
        self,
        http: httpx.AsyncClient,
        token: SecretStr,
        *,
        base_url: str = "https://api.telegram.org",
        sleep: Sleep = real_sleep,
        max_attempts: int = 4,
    ) -> None:
        self._http = http
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._max_attempts = max_attempts

    async def get_updates(
        self, offset: int | None, *, poll_timeout: int = POLL_TIMEOUT_S
    ) -> list[Update]:
        params: dict[str, Any] = {"timeout": poll_timeout, "allowed_updates": '["message"]'}
        if offset is not None:
            params["offset"] = offset
        result = await self._call(
            "getUpdates",
            params=params,
            http_timeout=httpx.Timeout(connect=3.0, read=poll_timeout + 10.0, write=10.0, pool=5.0),
            attempts=1,  # the polling loop owns retries for getUpdates
        )
        return [Update.model_validate(item) for item in result or []]

    async def send_message(self, chat_id: int, text: str) -> None:
        await self._call(
            "sendMessage",
            json={
                "chat_id": chat_id,
                "text": text[:MAX_MESSAGE_LEN],
                "link_preview_options": {"is_disabled": True},
            },
        )

    async def _call(
        self,
        method: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        http_timeout: httpx.Timeout | None = None,
        attempts: int | None = None,
    ) -> Any:
        max_attempts = attempts or self._max_attempts
        attempt = 0
        while True:
            attempt += 1
            try:
                return await self._once(method, params, json, http_timeout)
            except TelegramRetryAfterError as exc:
                if attempt >= max_attempts:
                    raise
                log.info("telegram_retry_after", method=method, retry_after=exc.retry_after)
                await self._sleep(exc.retry_after)
            except TelegramUnavailableError as exc:
                if attempt >= max_attempts or isinstance(exc, TelegramDeliveryUnknownError):
                    raise  # an unknown outcome is not retried here: it could double-send
                delay = backoff_delay(attempt)
                log.info("telegram_retry", method=method, attempt=attempt, delay_s=delay)
                await self._sleep(delay)

    async def _once(
        self,
        method: str,
        params: dict[str, Any] | None,
        json: dict[str, Any] | None,
        http_timeout: httpx.Timeout | None,
    ) -> Any:
        url = f"{self._base_url}/bot{self._token.get_secret_value()}/{method}"
        timeout: Any = http_timeout if http_timeout is not None else httpx.USE_CLIENT_DEFAULT
        try:
            if json is not None:
                response = await self._http.post(url, json=json, timeout=timeout)
            else:
                response = await self._http.get(url, params=params, timeout=timeout)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            # Never reached Telegram. The exception text is not used: it may carry the URL.
            raise TelegramUnavailableError(f"{method}: {type(exc).__name__}") from None
        except httpx.TransportError as exc:
            raise TelegramDeliveryUnknownError(f"{method}: {type(exc).__name__}") from None
        return _result(method, response)


def _result(method: str, response: httpx.Response) -> Any:
    try:
        envelope = _Envelope.model_validate(response.json())
    except ValueError:
        envelope = _Envelope(ok=False, error_code=response.status_code, description="non-JSON")
    if response.status_code == 429 or envelope.error_code == 429:
        retry_after = envelope.parameters.get("retry_after")
        raise TelegramRetryAfterError(float(retry_after) if retry_after is not None else 1.0)
    if response.status_code >= 500:
        raise TelegramUnavailableError(f"{method}: HTTP {response.status_code}")
    if not envelope.ok or response.status_code >= 400:
        raise TelegramError(envelope.error_code or response.status_code, envelope.description)
    return envelope.result
