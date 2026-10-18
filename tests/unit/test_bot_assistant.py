"""P5.7: the assistant with a scripted fake Anthropic planner and a respx-stubbed read API.

No test talks to Anthropic: the planner is a fake, and tests/conftest.py points the SDK's base
URL at an unroutable host as a backstop.
"""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from typing import Any

import anthropic
import httpx
import httpx2
import pytest
import respx
from anthropic.types.beta import BetaMessage, BetaMessageParam, BetaToolParam
from pydantic import SecretStr

from tests.conftest import make_settings
from tests.support.messages import NEUTRAL_EN as MSG
from trainsync.bot import main as bot_main
from trainsync.bot.assistant import (
    TOOLS,
    AnthropicPlanner,
    Assistant,
    system_prompt,
)
from trainsync.bot.messages import PACKS, Key, Messages, messages_for, using_lang
from trainsync.bot.read_api import ReadApi
from trainsync.coach.mode import CoachMode, MemorySoftModeStore, using_profanity
from trainsync.core.redis import create_redis
from trainsync.core.settings import BotTone

API = "http://trainsync-api"
NOW = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)

SEPTEMBER = {
    "from": "2026-09-01",
    "to": "2026-09-30",
    "sport_type": "Run",
    "totals": {
        "count": 14,
        "distance_m": 152340.0,
        "moving_time_s": 49800,
        "elevation_gain_m": 910.0,
    },
    "by_sport": [],
    "longest": None,
    "last_synced_at": "2026-10-18T08:30:00Z",
}
AUGUST = {
    **SEPTEMBER,
    "from": "2026-08-01",
    "to": "2026-08-31",
    "totals": {
        "count": 11,
        "distance_m": 118760.0,
        "moving_time_s": 39000,
        "elevation_gain_m": 700.0,
    },
}
STATUS = {
    "athletes": [],
    "webhooks": {
        "last_received_at": None,
        "last_processed_at": None,
        "pending": 0,
        "processing": 0,
        "failed": 0,
        "dead_letters": 0,
    },
    "rate_limit": None,
    "circuit": {"state": "closed", "processes": []},
    "last_synced_at": "2026-10-18T08:30:00Z",
}


def message(content: list[dict[str, Any]], stop_reason: str = "tool_use") -> BetaMessage:
    return BetaMessage.model_validate(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-5-5",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10},
        }
    )


def tool_use(call_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": call_id, "name": name, "input": arguments}


def text(value: str) -> BetaMessage:
    return message([{"type": "text", "text": value}], "end_turn")


Turn = Callable[[list[BetaMessageParam]], BetaMessage]


class ScriptedPlanner:
    """Plays one scripted turn per request and records what it was sent."""

    def __init__(self, turns: list[Turn | BetaMessage]) -> None:
        self._turns = list(turns)
        self.requests: list[list[BetaMessageParam]] = []
        self.systems: list[str] = []

    async def create(
        self, *, system: str, tools: list[BetaToolParam], messages: list[BetaMessageParam]
    ) -> BetaMessage:
        assert tools == TOOLS
        self.requests.append(list(messages))
        self.systems.append(system)
        turn = self._turns.pop(0) if len(self._turns) > 1 else self._turns[0]
        return turn if isinstance(turn, BetaMessage) else turn(messages)


def tool_results(messages: list[BetaMessageParam]) -> list[dict[str, Any]]:
    last = messages[-1]
    assert last["role"] == "user"
    content = last["content"]
    assert isinstance(content, list)
    return [dict(block) for block in content]  # type: ignore[call-overload]


class AllowAll:
    def __init__(self) -> None:
        self.asked: list[int] = []

    async def allow(self, chat_id: int) -> bool:
        self.asked.append(chat_id)
        return True


class DenyAll:
    async def allow(self, chat_id: int) -> bool:
        return False


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def api() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:

        def summary(request: httpx.Request) -> httpx.Response:
            body = {"2026-09-01": SEPTEMBER, "2026-08-01": AUGUST}[request.url.params["from"]]
            return httpx.Response(200, json=body)

        router.get(f"{API}/v1/stats/summary", name="summary").mock(side_effect=summary)
        router.get(f"{API}/v1/sync/status", name="status").mock(
            return_value=httpx.Response(200, json=STATUS)
        )
        router.get(f"{API}/v1/activities", name="activities").mock(
            return_value=httpx.Response(
                200, json={"items": [], "next_cursor": None, "last_synced_at": None}
            )
        )
        yield router


def assistant(http: httpx.AsyncClient, planner: ScriptedPlanner, **kwargs: Any) -> Assistant:
    read_api = ReadApi(http, API, SecretStr("bot-key"))
    return Assistant(
        planner,
        read_api,
        kwargs.pop("limiter", AllowAll()),
        lambda: NOW,
        kwargs.pop("msg", MSG),
        **kwargs,
    )


def answer_from_results(messages: list[BetaMessageParam]) -> BetaMessage:
    """What a grounded model does: read the numbers out of the tool results."""
    km = [
        json.loads(result["content"])["totals"]["distance_m"] / 1000
        for result in tool_results(messages)
    ]
    return text(f"September: {km[0]:.1f} km, August: {km[1]:.1f} km (+{km[0] - km[1]:.1f} km).")


async def test_tool_calls_run_against_the_api_and_the_answer_uses_its_numbers(
    http: httpx.AsyncClient, api: respx.MockRouter
) -> None:
    planner = ScriptedPlanner(
        [
            message(
                [
                    {"type": "text", "text": "Let me look that up."},
                    tool_use(
                        "tu_1",
                        "get_summary",
                        {"from": "2026-09-01", "to": "2026-09-30", "sport_type": "Run"},
                    ),
                    tool_use(
                        "tu_2",
                        "get_summary",
                        {"from": "2026-08-01", "to": "2026-08-31", "sport_type": "Run"},
                    ),
                ]
            ),
            answer_from_results,
        ]
    )
    reply = await assistant(http, planner).answer(
        42, "How many km did I run in September compared to August?"
    )
    assert reply == "September: 152.3 km, August: 118.8 km (+33.6 km)."

    calls = [c.request.url.params for c in api["summary"].calls]
    assert [(p["from"], p["to"], p["sport_type"]) for p in calls] == [
        ("2026-09-01", "2026-09-30", "Run"),
        ("2026-08-01", "2026-08-31", "Run"),
    ]
    results = tool_results(planner.requests[1])
    assert [r["tool_use_id"] for r in results] == ["tu_1", "tu_2"]
    assert all("is_error" not in r for r in results)
    assert json.loads(results[0]["content"])["last_synced_at"] == "2026-10-18T08:30:00Z"
    assert "Today is 2026-10-18 (Sunday)." in planner.systems[0]


@pytest.mark.parametrize(
    ("name", "arguments", "error"),
    [
        (
            "get_summary",
            {"from": "September", "to": "2026-09-30", "sport_type": None},
            "YYYY-MM-DD",
        ),
        ("get_summary", {"from": 1756684800, "to": "2026-09-30", "sport_type": None}, "YYYY-MM-DD"),
        ("get_weekly", {"from": "2026-09-30", "to": "2026-09-01", "sport_type": None}, "before"),
        ("get_weekly", {"from": "2000-01-01", "to": "2026-09-01", "sport_type": None}, "longer"),
        ("get_summary", {"from": "2026-02-30", "to": "2026-03-01", "sport_type": None}, "date"),
        ("get_summary", {"from": "2026-09-01", "to": "2026-09-30", "sql": "1"}, "Extra inputs"),
        ("list_activities", {"from": None, "to": None, "sport_type": None, "limit": 500}, "50"),
        ("get_sync_status", {"verbose": True}, "Extra inputs"),
        ("drop_tables", {}, "Unknown tool"),
    ],
)
async def test_invalid_arguments_are_reported_back_and_not_executed(
    http: httpx.AsyncClient,
    api: respx.MockRouter,
    name: str,
    arguments: dict[str, Any],
    error: str,
) -> None:
    planner = ScriptedPlanner([message([tool_use("tu_1", name, arguments)]), text("Sorry.")])
    assert await assistant(http, planner).answer(42, "?") == "Sorry."
    [result] = tool_results(planner.requests[1])
    assert result["is_error"] is True
    assert result["tool_use_id"] == "tu_1"
    assert error in result["content"]
    assert all(route.call_count == 0 for route in api.routes)


async def test_valid_list_and_status_calls(http: httpx.AsyncClient, api: respx.MockRouter) -> None:
    planner = ScriptedPlanner(
        [
            message(
                [
                    tool_use(
                        "tu_1",
                        "list_activities",
                        {"from": "2026-10-01", "to": None, "sport_type": "Ride", "limit": 5},
                    ),
                    tool_use("tu_2", "get_sync_status", {}),
                ]
            ),
            text("No rides yet this month."),
        ]
    )
    assert await assistant(http, planner).answer(42, "rides?") == "No rides yet this month."
    params = api["activities"].calls.last.request.url.params
    assert (params["from"], params["sport_type"], params["limit"]) == ("2026-10-01", "Ride", "5")
    assert "to" not in params
    listed, status = tool_results(planner.requests[1])
    assert "next_cursor" not in json.loads(listed["content"])
    assert json.loads(status["content"])["circuit"]["state"] == "closed"


async def test_api_failure_is_a_tool_error(http: httpx.AsyncClient, api: respx.MockRouter) -> None:
    api["status"].mock(return_value=httpx.Response(503))
    planner = ScriptedPlanner([message([tool_use("tu_1", "get_sync_status", {})]), text("Down.")])
    assert await assistant(http, planner).answer(42, "status?") == "Down."
    [result] = tool_results(planner.requests[1])
    assert result["is_error"] is True
    assert "HTTP 503" in result["content"]


async def test_tool_call_limit_is_enforced(http: httpx.AsyncClient, api: respx.MockRouter) -> None:
    counter = iter(range(100))

    def always_another_call(messages: list[BetaMessageParam]) -> BetaMessage:
        return message([tool_use(f"tu_{next(counter)}", "get_sync_status", {})])

    planner = ScriptedPlanner([always_another_call])
    reply = await assistant(http, planner, max_tool_calls=5).answer(42, "loop forever")
    assert reply == MSG(Key.ASSISTANT_TOO_MANY_CALLS)
    assert api["status"].call_count == 5  # the sixth call was refused, not executed
    [refused] = tool_results(planner.requests[-1])
    assert refused["is_error"] is True
    assert "limit" in refused["content"]
    assert len(planner.requests) == 7  # 5 executed + 1 refused + the one that gave up


async def test_answer_after_hitting_the_limit_is_returned(
    http: httpx.AsyncClient, api: respx.MockRouter
) -> None:
    many = message([tool_use(f"tu_{i}", "get_sync_status", {}) for i in range(4)])
    planner = ScriptedPlanner([many, many, text("Here is what I found.")])
    reply = await assistant(http, planner, max_tool_calls=5).answer(42, "?")
    assert reply == "Here is what I found."
    assert api["status"].call_count == 5
    assert [r.get("is_error", False) for r in tool_results(planner.requests[2])] == [
        False,
        True,
        True,
        True,
    ]


async def test_timeout_is_enforced(http: httpx.AsyncClient) -> None:
    class Hanging(ScriptedPlanner):
        async def create(
            self, *, system: str, tools: list[BetaToolParam], messages: list[BetaMessageParam]
        ) -> BetaMessage:
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    planner = Hanging([text("never")])
    assert await assistant(http, planner, timeout_s=0.01).answer(42, "?") == MSG(
        Key.ASSISTANT_TIMED_OUT
    )


async def test_rate_limited_chat_never_reaches_the_model(http: httpx.AsyncClient) -> None:
    planner = ScriptedPlanner([text("hello")])
    assert await assistant(http, planner, limiter=DenyAll()).answer(42, "?") == MSG(
        Key.ASSISTANT_RATE_LIMITED
    )
    assert planner.requests == []


async def test_tone_and_language_reach_the_prompt_and_the_canned_replies(
    http: httpx.AsyncClient, api: respx.MockRouter
) -> None:
    coach = Messages(PACKS["hardcore", "tr"])
    planner = ScriptedPlanner([text("Bu hafta 41.3 km.")])
    assert await assistant(http, planner, msg=coach).answer(42, "?") == "Bu hafta 41.3 km."
    system = planner.systems[0]
    assert "Reply in Turkish." in system
    assert "Koç" in system
    assert "never comment on the athlete's body" in system
    assert "Today is 2026-10-18 (Sunday)." in system
    denied = await assistant(http, planner, limiter=DenyAll(), msg=coach).answer(42, "?")
    assert denied == coach(Key.ASSISTANT_RATE_LIMITED)


def test_neutral_prompt_has_no_persona() -> None:
    prompt = system_prompt(NOW)
    assert "Reply in English." in prompt
    assert "Coach" not in prompt
    assert system_prompt(NOW, "neutral", "tr").count("Reply in Turkish.") == 1


async def test_refusal_and_api_errors(http: httpx.AsyncClient) -> None:
    refused = ScriptedPlanner([message([], "refusal")])
    assert await assistant(http, refused).answer(42, "?") == MSG(Key.ASSISTANT_REFUSED)

    class Broken(ScriptedPlanner):
        async def create(
            self, *, system: str, tools: list[BetaToolParam], messages: list[BetaMessageParam]
        ) -> BetaMessage:
            raise anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x.invalid"))

    assert await assistant(http, Broken([text("x")])).answer(42, "?") == MSG(
        Key.ASSISTANT_UNAVAILABLE
    )
    empty = ScriptedPlanner([message([], "end_turn")])
    assert await assistant(http, empty).answer(42, "?") == MSG(Key.ASSISTANT_UNAVAILABLE)


def test_tool_schemas_are_strict() -> None:
    assert [t["name"] for t in TOOLS] == [
        "get_summary",
        "get_weekly",
        "list_activities",
        "get_sync_status",
    ]
    for tool in TOOLS:
        assert tool.get("strict") is True
        schema = tool["input_schema"]
        assert isinstance(schema, dict)
        assert schema["additionalProperties"] is False
        assert set(schema.get("required") or []) == set(schema["properties"])  # type: ignore[arg-type]


async def test_anthropic_planner_request_shape() -> None:
    sent: dict[str, Any] = {}

    class FakeMessages:
        async def create(self, **kwargs: Any) -> BetaMessage:
            sent.update(kwargs)
            return text("ok")

    class FakeClient:
        class beta:  # noqa: N801  # mirrors the SDK's attribute name
            messages = FakeMessages()

    planner = AnthropicPlanner(FakeClient(), "claude-sonnet-5-5")  # type: ignore[arg-type]
    reply = await planner.create(
        system="s", tools=TOOLS, messages=[{"role": "user", "content": "q"}]
    )
    assert reply.content[0].type == "text"
    assert sent["model"] == "claude-sonnet-5-5"
    assert sent["tools"] == TOOLS
    assert sent["output_config"] == {"effort": "low"}
    assert sent["fallbacks"] == "default"
    assert sent["betas"] == ["server-side-fallback-2026-07-01"]
    assert "tool_choice" not in sent  # forced tool use is rejected by this model


async def test_text_handler_is_off_without_a_key(http: httpx.AsyncClient) -> None:
    read_api = ReadApi(http, API, SecretStr("k"))
    redis = create_redis(make_settings())  # lazy: never connects here
    async with AsyncExitStack() as stack:
        stack.push_async_callback(redis.aclose)
        off = await bot_main.text_handler(
            make_settings(), read_api, redis, stack, MSG, clock=lambda: NOW
        )
        assert off is None
        settings = make_settings(anthropic_api_key="sk-test-not-real")
        on = await bot_main.text_handler(settings, read_api, redis, stack, MSG, clock=lambda: NOW)
        assert on is not None


# ---------------------------------------------------------------- coach (P6.11, ADR 0030)


@pytest.mark.parametrize("tone", ["neutral", "hardcore"])
def test_guardrails_are_in_every_prompt_and_savage_only_on_request(tone: BotTone) -> None:
    plain = system_prompt(NOW, tone, "tr")
    assert "Hard limits" in plain
    assert "see a doctor" in plain
    assert "never push eating below their nutrition target" in plain
    assert "SAVAGE" not in plain
    savage = system_prompt(NOW, tone, "tr", savage=True)
    assert "The user explicitly asked for this tone" in savage
    assert "Profanity has no limit" in savage
    assert savage.index("Hard limits") < savage.index("SAVAGE")  # the limits override it


def test_a_null_last_synced_at_means_check_the_sync_status_first() -> None:
    """2026-10-18: the assistant called a running first sync 'no synced data' (P6.11 bug)."""
    prompt = system_prompt(NOW)
    assert "If it is null, call get_sync_status before answering" in prompt
    assert "the first sync is still in progress" in prompt
    assert "no Strava account is connected yet" in prompt


async def test_savage_reaches_the_prompt_and_soft_mode_takes_it_out(
    http: httpx.AsyncClient, api: respx.MockRouter
) -> None:
    soft = MemorySoftModeStore()
    planner = ScriptedPlanner([text("Kalk lan."), text("Kalk.")])
    coach = Messages(PACKS["hardcore", "tr"])
    bot = assistant(http, planner, msg=coach, mode=CoachMode(configured=True, soft=soft))
    assert await bot.answer(42, "?") == "Kalk lan."
    assert "SAVAGE" in planner.systems[0]
    await soft.soften()
    await bot.answer(42, "?")
    assert "SAVAGE" not in planner.systems[1]


@pytest.mark.parametrize(
    "reply",
    [
        "3 antrenman bu hafta, şişko.",
        "Burn it off tomorrow: 600 kcal over.",
        "Bugün aç kal, yarın telafi edersin.",
    ],
)
async def test_a_reply_that_breaks_a_guardrail_is_never_sent(
    http: httpx.AsyncClient, api: respx.MockRouter, reply: str
) -> None:
    planner = ScriptedPlanner([text(reply)])
    assert await assistant(http, planner).answer(42, "?") == MSG(Key.ASSISTANT_UNAVAILABLE)


async def test_profanity_in_a_reply_is_fine(http: httpx.AsyncClient, api: respx.MockRouter) -> None:
    reply = "Amına koyayım, bu hafta 3 antrenman. Siktir et bahaneyi, yarın 18:00."
    planner = ScriptedPlanner([text(reply)])
    assert await assistant(http, planner).answer(42, "?") == reply


async def test_the_chat_language_reaches_the_prompt(
    http: httpx.AsyncClient, api: respx.MockRouter
) -> None:
    """P6.12: `/lang` changes the reply language of the assistant at runtime (ADR 0031)."""
    msg = messages_for(make_settings(bot_lang="en"))
    planner = ScriptedPlanner([text("ok")])
    bot = assistant(http, planner, msg=msg)
    await bot.answer(42, "?")
    with using_lang("tr"):
        await bot.answer(42, "?")
    assert "Reply in English." in planner.systems[0]
    assert "Reply in Turkish." in planner.systems[1]


# ---------------------------------------------------------------- food and profanity (P6.13)


def test_max_profanity_is_in_the_prompt_only_with_savage_and_max() -> None:
    """ADR 0032: in max the assistant swears in every reply; the hard limits still win."""
    assert "Profanity: MAX" not in system_prompt(NOW, "hardcore", "tr", savage=True)
    assert "Profanity: MAX" not in system_prompt(NOW, "hardcore", "tr", profanity="max")
    maxed = system_prompt(NOW, "hardcore", "tr", savage=True, profanity="max")
    assert "Swear naturally in every reply" in maxed
    assert "praise and good news too" in maxed
    assert maxed.index("Hard limits") < maxed.index("Profanity: MAX")


def test_the_prompt_roasts_choices_and_keeps_distress_calm() -> None:
    plain = system_prompt(NOW, "hardcore", "en")
    assert "Food: eat it, log it" not in plain  # the old rule is gone (ADR 0032)
    assert "skipping meals or eating less to make up for it" in plain
    assert "throwing up, not eating, hating themselves or bingeing" in plain
    savage = system_prompt(NOW, "hardcore", "en", savage=True)
    assert "hard roast of the choice, never of the body" in savage
    assert "the day's kcal target stays the target" in savage


async def test_the_chat_profanity_reaches_the_prompt(
    http: httpx.AsyncClient, api: respx.MockRouter
) -> None:
    """`/swear max` changes the prompt at runtime; `BOT_PROFANITY` is the default."""
    planner = ScriptedPlanner([text("ok"), text("ok"), text("ok")])
    coach = Messages(PACKS["hardcore", "tr"])
    mode = CoachMode(configured=True, soft=MemorySoftModeStore())
    bot = assistant(http, planner, msg=coach, mode=mode)
    await bot.answer(42, "?")
    with using_profanity("max"):
        await bot.answer(42, "?")
    assert "Profanity: MAX" not in planner.systems[0]
    assert "Profanity: MAX" in planner.systems[1]
    default_max = assistant(http, planner, msg=coach, mode=mode, profanity="max")
    await default_max.answer(42, "?")
    assert "Profanity: MAX" in planner.systems[2]
