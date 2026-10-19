"""P5.6: the Notifier implementations and how the worker picks one."""

from collections.abc import AsyncIterator
from datetime import timedelta

import httpx
import pytest
import respx
from pydantic import SecretStr

from tests.conftest import make_settings
from tests.support.telegram import BOT_TOKEN, BOT_URL, TELEGRAM, SleepRecorder, error, ok
from trainsync.integrations.notifier import (
    DeliveryUnknownError,
    Notifier,
    NotifyFailedError,
    NullNotifier,
)
from trainsync.integrations.telegram.client import TelegramApi
from trainsync.integrations.telegram.notifier import TelegramNotifier
from trainsync.modules.notifications.tasks import build_notifier, retry_delay


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


def notifier(http: httpx.AsyncClient) -> TelegramNotifier:
    api = TelegramApi(
        http, SecretStr(BOT_TOKEN), base_url=TELEGRAM, sleep=SleepRecorder(), max_attempts=1
    )
    return TelegramNotifier(api)


@respx.mock
async def test_telegram_notifier_sends_to_the_chat(http: httpx.AsyncClient) -> None:
    route = respx.post(f"{BOT_URL}/sendMessage").mock(return_value=ok({}))
    target: Notifier = notifier(http)
    await target.send("-1001", "hello")
    assert route.calls.last.request.content.startswith(b'{"chat_id":-1001')


@respx.mock
@pytest.mark.parametrize(
    ("response", "raised", "retry_after"),
    [
        (error(429, "slow", retry_after=30), NotifyFailedError, 30.0),
        (httpx.Response(502), NotifyFailedError, None),
        (error(403, "blocked"), NotifyFailedError, None),
        (httpx.ConnectError("refused"), NotifyFailedError, None),
        (httpx.ReadTimeout("slow"), DeliveryUnknownError, None),
    ],
)
async def test_telegram_failures_map_to_notifier_errors(
    http: httpx.AsyncClient,
    response: httpx.Response | Exception,
    raised: type[Exception],
    retry_after: float | None,
) -> None:
    route = respx.post(f"{BOT_URL}/sendMessage")
    if isinstance(response, Exception):
        route.mock(side_effect=response)
    else:
        route.mock(return_value=response)
    with pytest.raises(raised) as exc_info:
        await notifier(http).send("1", "x")
    if isinstance(exc_info.value, NotifyFailedError):
        assert exc_info.value.retry_after == retry_after
    assert BOT_TOKEN not in str(exc_info.value)


async def test_null_notifier_sends_nothing() -> None:
    await NullNotifier().send("1", "x")
    assert NullNotifier.channel == "null"


async def test_build_notifier(http: httpx.AsyncClient) -> None:
    sleep = SleepRecorder()
    assert build_notifier(make_settings(), http, sleep)[1] is None
    no_chat = make_settings(telegram_bot_token=BOT_TOKEN)
    assert isinstance(build_notifier(no_chat, http, sleep)[0], NullNotifier)
    configured = make_settings(telegram_bot_token=BOT_TOKEN, telegram_allowed_chat_ids="5,6")
    chosen, chat_ref = build_notifier(configured, http, sleep)
    assert isinstance(chosen, TelegramNotifier)
    assert chat_ref == "5"


def test_retry_delay_grows() -> None:
    assert [retry_delay(n) for n in (1, 2, 3, 4)] == [
        timedelta(seconds=s) for s in (10, 30, 90, 270)
    ]
