"""P5.5: the Telegram client honours 429 `retry_after` and backs off on 5xx, via injected sleep."""

import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from pydantic import SecretStr

from tests.support.telegram import (
    BOT_TOKEN,
    BOT_URL,
    TELEGRAM,
    SleepRecorder,
    error,
    message_update,
    ok,
    sent_messages,
)
from trainsync.integrations.telegram.client import (
    Button,
    TelegramApi,
    TelegramDeliveryUnknownError,
    TelegramError,
    TelegramRetryAfterError,
    TelegramUnavailableError,
    backoff_delay,
    keyboard_markup,
)


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


def api(http: httpx.AsyncClient, sleep: SleepRecorder, **kwargs: int) -> TelegramApi:
    return TelegramApi(http, SecretStr(BOT_TOKEN), base_url=TELEGRAM, sleep=sleep, **kwargs)


@respx.mock
async def test_429_waits_exactly_retry_after_then_sends_once(http: httpx.AsyncClient) -> None:
    route = respx.post(f"{BOT_URL}/sendMessage").mock(
        side_effect=[error(429, "Too Many Requests: retry after 7", retry_after=7), ok({})]
    )
    sleep = SleepRecorder()
    await api(http, sleep).send_message(42, "hi")
    assert sleep.sleeps == [7.0]  # one wait of exactly retry_after, no busy loop
    assert route.call_count == 2
    assert sent_messages(route) == [
        {"chat_id": 42, "text": "hi", "link_preview_options": {"is_disabled": True}}
    ]


@respx.mock
async def test_429_until_attempts_run_out_raises_retry_after(http: httpx.AsyncClient) -> None:
    route = respx.post(f"{BOT_URL}/sendMessage").mock(
        return_value=error(429, "Too Many Requests", retry_after=3)
    )
    sleep = SleepRecorder()
    with pytest.raises(TelegramRetryAfterError) as exc_info:
        await api(http, sleep, max_attempts=3).send_message(42, "hi")
    assert exc_info.value.retry_after == 3
    assert route.call_count == 3
    assert sleep.sleeps == [3.0, 3.0]


@respx.mock
async def test_5xx_and_connect_errors_back_off_exponentially(http: httpx.AsyncClient) -> None:
    route = respx.post(f"{BOT_URL}/sendMessage").mock(
        side_effect=[
            httpx.Response(502),
            httpx.ConnectError("refused"),
            error(500, "Internal"),
            ok({}),
        ]
    )
    sleep = SleepRecorder()
    await api(http, sleep).send_message(42, "hi")
    assert sleep.sleeps == [1.0, 2.0, 4.0]
    assert route.call_count == 4


@respx.mock
async def test_unavailable_after_max_attempts(http: httpx.AsyncClient) -> None:
    respx.post(f"{BOT_URL}/sendMessage").mock(return_value=httpx.Response(503))
    with pytest.raises(TelegramUnavailableError) as exc_info:
        await api(http, SleepRecorder(), max_attempts=2).send_message(42, "hi")
    assert BOT_TOKEN not in str(exc_info.value)


@respx.mock
async def test_read_timeout_is_an_unknown_outcome_and_not_retried(
    http: httpx.AsyncClient,
) -> None:
    route = respx.post(f"{BOT_URL}/sendMessage").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(TelegramDeliveryUnknownError) as exc_info:
        await api(http, SleepRecorder()).send_message(42, "hi")
    assert route.call_count == 1
    assert BOT_TOKEN not in str(exc_info.value)


@respx.mock
async def test_4xx_is_not_retried(http: httpx.AsyncClient) -> None:
    route = respx.post(f"{BOT_URL}/sendMessage").mock(
        return_value=error(400, "Bad Request: chat not found")
    )
    with pytest.raises(TelegramError) as exc_info:
        await api(http, SleepRecorder()).send_message(42, "hi")
    assert exc_info.value.status == 400
    assert route.call_count == 1


@respx.mock
async def test_non_json_error_body(http: httpx.AsyncClient) -> None:
    respx.post(f"{BOT_URL}/sendMessage").mock(return_value=httpx.Response(404, text="nope"))
    with pytest.raises(TelegramError, match="404"):
        await api(http, SleepRecorder()).send_message(42, "hi")


@respx.mock
async def test_long_messages_are_truncated(http: httpx.AsyncClient) -> None:
    route = respx.post(f"{BOT_URL}/sendMessage").mock(return_value=ok({}))
    await api(http, SleepRecorder()).send_message(42, "x" * 5000)
    assert len(sent_messages(route)[0]["text"]) == 4096


@respx.mock
async def test_get_updates_parses_messages_and_passes_offset(http: httpx.AsyncClient) -> None:
    route = respx.get(f"{BOT_URL}/getUpdates").mock(
        return_value=ok([message_update(5, 42, "/week"), {"update_id": 6}])
    )
    updates = await api(http, SleepRecorder()).get_updates(5, poll_timeout=1)
    assert [u.update_id for u in updates] == [5, 6]
    assert updates[0].message is not None
    assert updates[0].message.text == "/week"
    assert updates[1].message is None
    params = route.calls.last.request.url.params
    assert (params["offset"], params["timeout"]) == ("5", "1")


@respx.mock
async def test_get_updates_does_not_retry_itself(http: httpx.AsyncClient) -> None:
    route = respx.get(f"{BOT_URL}/getUpdates").mock(
        return_value=error(429, "slow down", retry_after=4)
    )
    sleep = SleepRecorder()
    with pytest.raises(TelegramRetryAfterError):
        await api(http, sleep).get_updates(None)
    assert route.call_count == 1
    assert sleep.sleeps == []


def test_backoff_is_capped() -> None:
    assert [backoff_delay(n) for n in (1, 2, 3)] == [1.0, 2.0, 4.0]
    assert backoff_delay(20) == 30.0


# ---------------------------------------------------------------- buttons (P6.9)


@respx.mock
async def test_polling_asks_for_button_presses_too(http: httpx.AsyncClient) -> None:
    route = respx.get(f"{BOT_URL}/getUpdates").mock(
        return_value=ok(
            [
                {
                    "update_id": 5,
                    "callback_query": {
                        "id": "cq-1",
                        "from": {"id": 42},
                        "data": "ci:20261018:0:s:done",
                        "message": {"message_id": 9, "chat": {"id": 42}, "text": "Q"},
                    },
                }
            ]
        )
    )
    [update] = await api(http, SleepRecorder()).get_updates(None, poll_timeout=0)
    params = route.calls.last.request.url.params
    assert params["allowed_updates"] == '["message","callback_query"]'
    assert update.callback_query is not None
    assert update.callback_query.data == "ci:20261018:0:s:done"
    assert update.callback_query.message is not None
    assert update.callback_query.message.message_id == 9


@respx.mock
async def test_inline_keyboard_answer_and_removal(http: httpx.AsyncClient) -> None:
    send = respx.post(f"{BOT_URL}/sendMessage").mock(return_value=ok({}))
    answer = respx.post(f"{BOT_URL}/answerCallbackQuery").mock(return_value=ok(True))
    edit = respx.post(f"{BOT_URL}/editMessageReplyMarkup").mock(return_value=ok(True))
    client = api(http, SleepRecorder())
    keyboard = ((Button("Yes", "y"), Button("No", "n")), (Button("Skip", "s"),))
    await client.send_message(42, "Q?", keyboard)
    await client.answer_callback_query("cq-1", "Saved")
    await client.answer_callback_query("cq-2")
    await client.remove_keyboard(42, 9)
    assert sent_messages(send)[0]["reply_markup"] == {
        "inline_keyboard": [
            [{"text": "Yes", "callback_data": "y"}, {"text": "No", "callback_data": "n"}],
            [{"text": "Skip", "callback_data": "s"}],
        ]
    }
    bodies = [json.loads(c.request.content) for c in answer.calls]
    assert bodies == [{"callback_query_id": "cq-1", "text": "Saved"}, {"callback_query_id": "cq-2"}]
    assert json.loads(edit.calls.last.request.content) == {
        "chat_id": 42,
        "message_id": 9,
        "reply_markup": {"inline_keyboard": []},
    }


def test_callback_data_is_limited_to_64_bytes() -> None:
    with pytest.raises(ValueError, match="64 bytes"):
        keyboard_markup(((Button("x", "y" * 65),),))
