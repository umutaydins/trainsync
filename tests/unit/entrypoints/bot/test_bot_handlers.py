"""P5.5: command handling against a fake Telegram API and a stubbed read API (both respx)."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from prometheus_client import REGISTRY
from pydantic import SecretStr

from tests.conftest import make_settings
from tests.support.chat_links import ChatLinksApi, chat_links
from tests.support.messages import NEUTRAL_EN as MSG
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
from trainsync.entrypoints.bot import main as bot_main
from trainsync.entrypoints.bot.dispatcher import (
    Commands,
    Dispatcher,
    UsageError,
    parse_command,
    parse_stats_args,
    period_range,
    week_ranges,
)
from trainsync.entrypoints.bot.polling import Poller
from trainsync.integrations.telegram.client import TelegramApi, Update
from trainsync.modules.chat.assistant import Asker
from trainsync.modules.chat.read_api import ReadApi
from trainsync.modules.coach.packs import Key, NeutralKey

FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parents[3] / "fixtures" / "bot_api_responses.json").read_text(encoding="utf-8")
)
NOW = datetime.fromisoformat(FIXTURE["now"])  # Thursday 2026-10-15
API = "http://trainsync-api"
ALLOWED, STRANGER = 42, 99
DASHBOARD = "https://dash.example"


def metric(command: str, outcome: str) -> float:
    labels = {"command": command, "outcome": outcome}
    return REGISTRY.get_sample_value("bot_updates_total", labels) or 0.0


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def sleep() -> SleepRecorder:
    return SleepRecorder()


@pytest.fixture
def telegram(http: httpx.AsyncClient, sleep: SleepRecorder) -> TelegramApi:
    return TelegramApi(http, SecretStr(BOT_TOKEN), base_url=TELEGRAM, sleep=sleep)


@pytest.fixture
def dispatcher(http: httpx.AsyncClient, telegram: TelegramApi) -> Dispatcher:
    read_api = ReadApi(http, API, SecretStr("bot-key"))
    links = chat_links(http, API, lambda: NOW)
    return Dispatcher(
        telegram, Commands(read_api, lambda: NOW, MSG), links, MSG, dashboard_url=DASHBOARD
    )


@pytest.fixture
def fake_api() -> respx.MockRouter:
    """The read API, answering from the fixture file."""
    with respx.mock(assert_all_called=False) as router:
        summaries = {
            "2026-10-12": FIXTURE["summary_this_week"],
            "2026-10-05": FIXTURE["summary_last_week"],
            "2026-07-27": FIXTURE["summary_12w_run"],
        }

        def summary(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=summaries[request.url.params["from"]])

        router.get(f"{API}/v1/stats/summary", name="summary").mock(side_effect=summary)
        router.get(f"{API}/v1/stats/weekly", name="weekly").mock(
            return_value=httpx.Response(200, json=FIXTURE["weekly_12w_run"])
        )
        router.get(f"{API}/v1/activities", name="activities").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [FIXTURE["activity_run"]],
                    "next_cursor": None,
                    "last_synced_at": FIXTURE["now"],
                },
            )
        )
        router.get(f"{API}/v1/sync/status", name="status").mock(
            return_value=httpx.Response(200, json=FIXTURE["sync_status_healthy"])
        )
        ChatLinksApi().link(ALLOWED).install(router, API)
        yield router


@pytest.fixture
def send(fake_api: respx.MockRouter) -> respx.Route:
    return fake_api.post(f"{BOT_URL}/sendMessage").mock(return_value=ok({}))


def update(chat_id: int, text: str, update_id: int = 1) -> Update:
    return Update.model_validate(message_update(update_id, chat_id, text))


async def test_a_linked_chat_gets_the_reply_others_only_the_link_hint(
    dispatcher: Dispatcher, fake_api: respx.MockRouter, send: respx.Route
) -> None:
    """ADR 0036: an unknown chat runs nothing and is pointed to the dashboard."""
    denied_before = metric("week", "denied")
    ok_before = metric("week", "ok")

    await dispatcher.handle(update(STRANGER, "/week"))
    [hint] = sent_messages(send)
    assert (hint["chat_id"], hint["text"]) == (
        STRANGER,
        MSG.neutral(NeutralKey.LINK_HINT, url=DASHBOARD),
    )
    assert fake_api["summary"].call_count == 0  # not even the API is asked
    assert metric("week", "denied") - denied_before == 1

    send.reset()
    await dispatcher.handle(update(ALLOWED, "/week"))
    [message] = sent_messages(send)
    assert message["chat_id"] == ALLOWED
    assert message["text"].startswith("This week (12-15 Oct)\n3 activities · 41.3 km")
    assert "Last week (5-11 Oct)" in message["text"]
    assert metric("week", "ok") - ok_before == 1
    froms = [c.request.url.params["from"] for c in fake_api["summary"].calls]
    tos = [c.request.url.params["to"] for c in fake_api["summary"].calls]
    assert (froms, tos) == (["2026-10-12", "2026-10-05"], ["2026-10-15", "2026-10-11"])
    last = fake_api["summary"].calls.last.request
    assert (last.headers["X-API-Key"], last.headers["X-Acting-User"]) == ("bot-key", "1")


async def test_poller_replies_to_linked_chats_and_advances_offset(
    telegram: TelegramApi, dispatcher: Dispatcher, fake_api: respx.MockRouter, send: respx.Route
) -> None:
    get_updates = fake_api.get(f"{BOT_URL}/getUpdates").mock(
        side_effect=[
            ok([message_update(7, STRANGER, "/status"), message_update(8, ALLOWED, "/status")]),
            ok([]),
        ]
    )
    poller = Poller(telegram, dispatcher, poll_timeout=0)
    assert await poller.poll_once() == 0.0
    assert [m["chat_id"] for m in sent_messages(send)] == [STRANGER, ALLOWED]
    assert sent_messages(send)[1]["text"].startswith("✅ synced 20 min ago")
    assert poller.offset == 9
    await poller.poll_once()
    assert get_updates.calls.last.request.url.params["offset"] == "9"


@pytest.mark.parametrize(
    ("text", "expected_start"),
    [
        ("/start", MSG.help()),
        ("/help@trainsync_bot", MSG.help()),
        ("/last", "🏃 Morning Run"),
        ("/stats 12w run", "Last 12w · Run (27 Jul - 15 Oct)"),
        ("/nope", "Unknown command /nope."),
        ("how was my week?", MSG(Key.NO_ASSISTANT, help=MSG.help())),
        ("/stats run ride", "Usage: /stats"),
    ],
)
async def test_commands(
    dispatcher: Dispatcher, send: respx.Route, text: str, expected_start: str
) -> None:
    await dispatcher.handle(update(ALLOWED, text))
    [message] = sent_messages(send)
    assert message["text"].startswith(expected_start)


async def test_stats_queries_summary_and_weekly_with_the_same_range(
    dispatcher: Dispatcher, fake_api: respx.MockRouter, send: respx.Route
) -> None:
    await dispatcher.handle(update(ALLOWED, "/stats run 12w"))
    for name in ("summary", "weekly"):
        params = fake_api[name].calls.last.request.url.params
        assert (params["from"], params["to"], params["sport_type"]) == (
            "2026-07-27",
            "2026-10-15",
            "Run",
        )
    assert "Best week: 14 Sep · 52.0 km" in sent_messages(send)[0]["text"]


async def test_api_down_gets_a_friendly_reply(
    dispatcher: Dispatcher, fake_api: respx.MockRouter, send: respx.Route
) -> None:
    fake_api["status"].mock(return_value=httpx.Response(503))
    fake_api["activities"].mock(side_effect=httpx.ConnectError("down"))
    await dispatcher.handle(update(ALLOWED, "/status"))
    await dispatcher.handle(update(ALLOWED, "/last"))
    assert [m["text"] for m in sent_messages(send)] == [MSG(Key.API_DOWN), MSG(Key.API_DOWN)]


async def test_failed_reply_is_logged_not_raised(
    dispatcher: Dispatcher, fake_api: respx.MockRouter
) -> None:
    fake_api.post(f"{BOT_URL}/sendMessage").mock(return_value=error(403, "bot was blocked"))
    before = metric("help", "send_failed")
    await dispatcher.handle(update(ALLOWED, "/help"))
    assert metric("help", "send_failed") - before == 1


async def test_updates_without_text_are_ignored(dispatcher: Dispatcher, send: respx.Route) -> None:
    await dispatcher.handle(Update.model_validate({"update_id": 3}))
    assert send.call_count == 0


async def test_plain_text_goes_to_the_text_handler(
    telegram: TelegramApi, http: httpx.AsyncClient, send: respx.Route
) -> None:
    seen: list[tuple[int, str, Asker]] = []

    async def assistant(chat_id: int, text: str, asker: Asker) -> str:
        seen.append((chat_id, text, asker))
        return "42 km"

    read_api = ReadApi(http, API, SecretStr("k"))
    dispatcher = Dispatcher(
        telegram,
        Commands(read_api, lambda: NOW, MSG),
        chat_links(http, API, lambda: NOW),
        MSG,
        assistant,
    )
    await dispatcher.handle(update(ALLOWED, "how far did I run?"))
    zone = make_settings().checkin_tz  # the owner never chose a time zone
    assert seen == [(ALLOWED, "how far did I run?", Asker(1, zone, unlimited=True))]
    assert sent_messages(send)[0]["text"] == "42 km"


async def test_poll_429_is_honoured_without_a_busy_loop(
    telegram: TelegramApi,
    dispatcher: Dispatcher,
    fake_api: respx.MockRouter,
    send: respx.Route,
    sleep: SleepRecorder,
) -> None:
    stop = asyncio.Event()
    get_updates = fake_api.get(f"{BOT_URL}/getUpdates").mock(
        side_effect=[
            error(429, "Too Many Requests: retry after 9", retry_after=9),
            httpx.Response(502),
            ok([message_update(1, ALLOWED, "/help")]),
        ]
    )

    async def recording_sleep(seconds: float) -> None:
        await sleep(seconds)

    async def stop_after_reply(request: httpx.Request) -> httpx.Response:
        stop.set()
        return ok({})

    send.mock(side_effect=stop_after_reply)
    poller = Poller(telegram, dispatcher, sleep=recording_sleep, poll_timeout=0)
    await asyncio.wait_for(poller.run(stop), timeout=5)
    assert sleep.sleeps == [9.0, 1.0]  # retry_after, then the first 5xx backoff step
    assert get_updates.call_count == 3
    assert send.call_count == 1


async def test_stop_cancels_a_pending_long_poll(
    telegram: TelegramApi, dispatcher: Dispatcher, fake_api: respx.MockRouter
) -> None:
    stop = asyncio.Event()
    started = asyncio.Event()

    async def hang(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.Event().wait()  # a long poll that never returns
        raise AssertionError("unreachable")

    fake_api.get(f"{BOT_URL}/getUpdates").mock(side_effect=hang)
    task = asyncio.create_task(Poller(telegram, dispatcher).run(stop))
    await asyncio.wait_for(started.wait(), timeout=5)
    stop.set()
    await asyncio.wait_for(task, timeout=5)


def test_parse_command() -> None:
    assert parse_command("/Stats@my_bot 12w Run") == ("stats", ["12w", "Run"])
    assert parse_command("  hello /week") == (None, [])


def test_parse_stats_args() -> None:
    assert parse_stats_args([]) == ("4w", None)
    assert parse_stats_args(["52W"]) == ("52w", None)
    assert parse_stats_args(["trailrun", "12w"]) == ("12w", "TrailRun")
    assert parse_stats_args(["kitesurf"]) == ("4w", "Kitesurf")
    with pytest.raises(UsageError):
        parse_stats_args(["run", "ride"])


def test_ranges() -> None:
    assert week_ranges(date(2026, 10, 15)) == (
        (date(2026, 10, 12), date(2026, 10, 15)),
        (date(2026, 10, 5), date(2026, 10, 11)),
    )
    assert week_ranges(date(2026, 10, 12))[0] == (date(2026, 10, 12), date(2026, 10, 12))
    assert period_range(date(2026, 10, 15), 4) == (date(2026, 9, 21), date(2026, 10, 15))


async def test_main_without_token_idles_until_stopped() -> None:
    settings = make_settings(telegram_bot_token="", bot_metrics_port=0)
    stop = asyncio.Event()
    task = asyncio.create_task(bot_main.run(settings, stop))
    await asyncio.sleep(0)
    assert not task.done()
    stop.set()
    await asyncio.wait_for(task, timeout=5)


@respx.mock
async def test_main_with_token_polls_and_replies() -> None:
    settings = make_settings(
        telegram_bot_token=BOT_TOKEN,
        telegram_api_base_url=TELEGRAM,
        telegram_allowed_chat_ids="42, 43",
        bot_api_base_url=API,
        bot_metrics_port=0,
    )
    assert settings.telegram_allowed_chat_ids == [42, 43]
    stop = asyncio.Event()
    respx.get(f"{BOT_URL}/getUpdates").mock(
        side_effect=[ok([message_update(1, ALLOWED, "/help")]), ok([])]
    )

    def reply(request: httpx.Request) -> httpx.Response:
        stop.set()
        return ok({})

    send = respx.post(f"{BOT_URL}/sendMessage").mock(side_effect=reply)
    # The chat's user chose Turkish (P6.12); help stays English in every language.
    ChatLinksApi().link(ALLOWED, lang="tr").install(respx.mock, API)
    await asyncio.wait_for(bot_main.run(settings, stop, sleep=SleepRecorder()), timeout=5)
    assert sent_messages(send)[0]["text"] == MSG.help()


async def test_link_and_unlink_from_the_chat(
    http: httpx.AsyncClient, telegram: TelegramApi
) -> None:
    """P8.4, ADR 0036: `/link CODE` binds an unknown chat once; `/unlink` ends it."""
    with respx.mock(assert_all_called=False) as router:
        links = ChatLinksApi()
        links.codes["K7Q2M9XD"] = 5
        links.names[5] = "Ayşe"
        links.install(router, API)
        replies = router.post(f"{BOT_URL}/sendMessage").mock(return_value=ok({}))
        read_api = ReadApi(http, API, SecretStr("bot-key"))
        bot = Dispatcher(
            telegram,
            Commands(read_api, lambda: NOW, MSG),
            chat_links(http, API, lambda: NOW),
            MSG,
            dashboard_url=DASHBOARD,
        )
        texts: list[str] = []
        for n, text in enumerate(
            ["/link", "/link WRONG234", "/link k7q2m9xd", "/link K7Q2M9XD", "/unlink", "/week"]
        ):
            await bot.handle(update(STRANGER, text, n + 1))
            texts.append(sent_messages(replies)[-1]["text"])
    neutral = MSG.neutral
    assert texts == [
        neutral(NeutralKey.LINK_USAGE),
        neutral(NeutralKey.LINK_INVALID),
        neutral(NeutralKey.LINK_DONE, name="Ayşe"),
        neutral(NeutralKey.LINK_ALREADY),
        neutral(NeutralKey.UNLINKED),
        neutral(NeutralKey.LINK_HINT, url=DASHBOARD),
    ]
    assert links.chats == {}


async def test_the_dashboard_deep_link_links_the_chat(
    http: httpx.AsyncClient, telegram: TelegramApi
) -> None:
    """`t.me/<bot>?start=CODE` makes Telegram send `/start CODE`; a bare `/start` gets the hint."""
    with respx.mock(assert_all_called=False) as router:
        links = ChatLinksApi()
        links.codes["K7Q2M9XD"] = 5
        links.names[5] = "Ayşe"
        links.install(router, API)
        replies = router.post(f"{BOT_URL}/sendMessage").mock(return_value=ok({}))
        read_api = ReadApi(http, API, SecretStr("bot-key"))
        bot = Dispatcher(
            telegram,
            Commands(read_api, lambda: NOW, MSG),
            chat_links(http, API, lambda: NOW),
            MSG,
            dashboard_url=DASHBOARD,
        )
        texts: list[str] = []
        for n, text in enumerate(["/start", "/start K7Q2M9XD"]):
            await bot.handle(update(STRANGER, text, n + 1))
            texts.append(sent_messages(replies)[-1]["text"])
    assert texts == [
        MSG.neutral(NeutralKey.LINK_HINT, url=DASHBOARD),
        MSG.neutral(NeutralKey.LINK_DONE, name="Ayşe"),
    ]
    assert links.chats == {STRANGER: 5}
