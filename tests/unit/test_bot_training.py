"""P6.8: `/today`, `/plates`, `/log`, `/done`, `/eat`, `/kcal`, `/weight` against the fake Telegram
API and a stubbed trainsync API (both respx), plus the parsers they share with the check-in."""

import random
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from pydantic import SecretStr

from tests.support.bot_api import API, FakeApi, install, planned
from tests.support.messages import NEUTRAL_EN as MSG
from tests.support.state import MemoryStateStore
from tests.support.telegram import (
    BOT_TOKEN,
    BOT_URL,
    TELEGRAM,
    SleepRecorder,
    message_update,
    ok,
    sent_messages,
)
from trainsync.bot.common import client_id, kg, number, sets_text, thousands
from trainsync.bot.handlers import Commands, Dispatcher
from trainsync.bot.messages import PACKS, Messages
from trainsync.bot.nutrition import NutritionCommands, meal_at
from trainsync.bot.parsing import (
    ParsedSet,
    ParseError,
    parse_choice,
    parse_eat,
    parse_log,
    parse_number,
    parse_sets,
)
from trainsync.bot.read_api import ReadApi
from trainsync.bot.telegram import TelegramApi, Update
from trainsync.bot.training import TrainingCommands
from trainsync.db.models import Meal

NOW = datetime(2026, 10, 18, 15, 0, tzinfo=UTC)  # 18:00 in Istanbul, Sunday
ZONE = ZoneInfo("Europe/Istanbul")
CHAT = 42


def bw(reps: int) -> ParsedSet:
    return ParsedSet(Decimal(0), reps)


def at(weight: str, reps: int) -> ParsedSet:
    return ParsedSet(Decimal(weight), reps)


# ---------------------------------------------------------------- parsers


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("80x5x3", [at("80", 5)] * 3),
        ("80x5", [at("80", 5)]),
        ("80x5,5,4", [at("80", 5), at("80", 5), at("80", 4)]),
        ("bw x12x3", [bw(12)] * 3),
        ("BW x 12 x 3", [bw(12)] * 3),
        ("82.5\u00d75\u00d72", [at("82.5", 5)] * 2),
        ("82.25*8", [at("82.25", 8)]),
        ("100 x 1", [at("100", 1)]),
    ],
)
def test_parse_sets_valid(text: str, expected: list[ParsedSet]) -> None:
    assert parse_sets(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "80",
        "80x",
        "x5x3",
        "80x0",
        "80x101",
        "80x5,5x3",  # ambiguous: a rep list and a set count
        "80x5x21",
        "80.1x5",  # not a 0.25 kg step
        "501x1",
        "80kgx5",
        "eighty x5",
        "80x5x0",
    ],
)
def test_parse_sets_invalid(text: str) -> None:
    with pytest.raises(ParseError):
        parse_sets(text)


def test_parse_log() -> None:
    assert parse_log(["bench", "80x5x3"]) == ("bench", [at("80", 5)] * 3)
    assert parse_log(["bench", "press", "80", "x", "5", "x", "3"]) == (
        "bench press",
        [at("80", 5)] * 3,
    )
    assert parse_log(["pullup", "bw", "x12x3"]) == ("pullup", [bw(12)] * 3)
    assert parse_log(["squat", "100x5,5,4"])[1] == [at("100", 5), at("100", 5), at("100", 4)]
    for args in ([], ["80x5x3"], ["bench"], ["bench", "heavy"]):
        with pytest.raises(ParseError):
            parse_log(args)


def test_parse_eat() -> None:
    assert parse_eat(["oats", "60"]) == ("oats", Decimal(60))
    assert parse_eat(["greek", "yogurt", "150g"]) == ("greek yogurt", Decimal(150))
    assert parse_eat(["greek", "yogurt", "150", "g"]) == ("greek yogurt", Decimal(150))
    assert parse_eat(["rice", "72,5"]) == ("rice", Decimal("72.5"))
    for args in ([], ["60"], ["oats"], ["oats", "lots"], ["oats", "0"], ["oats", "6000"]):
        with pytest.raises(ParseError):
            parse_eat(args)


def test_parse_number_and_choice() -> None:
    assert parse_number("78,4") == Decimal("78.4")
    assert parse_number(" 7.5 ") == Decimal("7.5")
    assert parse_number("-3") is None
    assert parse_number("abc") is None
    assert parse_choice("2", 3) == 1
    assert parse_choice("1.", 3) == 0
    assert parse_choice("bench", 3) is None
    with pytest.raises(ParseError):
        parse_choice("4", 3)


def test_formatting_helpers() -> None:
    assert kg(Decimal("80.00")) == "80 kg"
    assert kg(82.5) == "82.5 kg"
    assert number(Decimal("1.25")) == "1.25"
    assert number(-0.0) == "0"
    assert number(120.2, 0) == "120"
    assert number(Decimal(100)) == "100"
    assert thousands(8240.4) == "8,240 kg"
    assert sets_text([at("80", 5), at("80", 5), at("80", 4)]) == "80 kg x 5, 5, 4"
    assert sets_text([bw(12)] * 2) == "bw x 12, 12"
    assert sets_text([at("80", 5), at("85", 3)]) == "80 kg x 5, 85 kg x 3"
    assert sets_text([]) == ""


@pytest.mark.parametrize(
    ("hour", "meal"),
    [(3, Meal.SNACK), (7, Meal.BREAKFAST), (12, Meal.LUNCH), (16, Meal.SNACK), (19, Meal.DINNER)],
)
def test_meal_by_local_hour(hour: int, meal: Meal) -> None:
    assert meal_at(hour) == meal


def test_client_ids_are_deterministic() -> None:
    assert client_id("tg:42:7:0") == client_id("tg:42:7:0")
    assert client_id("tg:42:7:0") != client_id("tg:42:7:1")


# ---------------------------------------------------------------- handlers


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{BOT_URL}/sendMessage", name="send").mock(return_value=ok({}))
        yield mock


@pytest.fixture
def fake(router: respx.MockRouter) -> FakeApi:
    return install(router, lambda: NOW)


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def store() -> MemoryStateStore:
    return MemoryStateStore()


def make_dispatcher(
    http: httpx.AsyncClient, store: MemoryStateStore, msg: Messages = MSG
) -> Dispatcher:
    telegram = TelegramApi(http, SecretStr(BOT_TOKEN), base_url=TELEGRAM, sleep=SleepRecorder())
    api = ReadApi(http, API, SecretStr("bot-key"))
    clock = lambda: NOW  # noqa: E731
    return Dispatcher(
        telegram,
        Commands(api, clock, msg),
        {CHAT},
        msg,
        features=[
            TrainingCommands(api, store, clock, ZONE, msg),
            NutritionCommands(api, store, clock, ZONE, msg),
        ],
    )


@pytest.fixture
def dispatcher(http: httpx.AsyncClient, store: MemoryStateStore) -> Dispatcher:
    return make_dispatcher(http, store)


def update(text: str, update_id: int = 1, chat_id: int = CHAT) -> Update:
    return Update.model_validate(message_update(update_id, chat_id, text))


def replies(router: respx.MockRouter) -> list[str]:
    return [m["text"] for m in sent_messages(router["send"])]


async def say(dispatcher: Dispatcher, router: respx.MockRouter, text: str, update_id: int) -> str:
    await dispatcher.handle(update(text, update_id))
    return replies(router)[-1]


async def test_today_without_a_program(
    dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi
) -> None:
    reply = await say(dispatcher, router, "/today", 1)
    assert reply == "No active program. Create one on the web, or log freely with /log."


async def test_today_shows_the_plan_with_suggested_weights(
    dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi
) -> None:
    fake.with_program(11, planned(20, 3, 8, 12, 80.0), planned(38, 3, 6, 6, None))
    reply = await say(dispatcher, router, "/today", 1)
    assert reply == (
        "Today: Upper/Lower · Upper A\n"
        "• Bench Press: 3 x 8-12 · 80 kg\n"
        "• Pull-Up: 3 x 6 · bw\n"
        "Log with /log, finish with /done."
    )


async def test_today_shows_progress_of_an_open_workout(
    dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi
) -> None:
    fake.with_program(11, planned(20, 3, 8, 12, 80.0))
    await fake_start(fake, program_day_id=11)
    await say(dispatcher, router, "/log bench 80x5x2", 1)
    reply = await say(dispatcher, router, "/today", 2)
    assert "In progress: 2 sets logged." in reply


async def fake_start(fake: FakeApi, program_day_id: int | None = None) -> int:
    from tests.support.bot_api import Workout

    workout = Workout(id=fake.next_workout_id, started_at=NOW, program_day_id=program_day_id)
    fake.next_workout_id += 1
    fake.workouts[workout.id] = workout
    return workout.id


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/plates 102.5", "102.5 kg: 25 + 15 + 1.25 kg per side (bar 20 kg)"),
        ("/plates 20", "20 kg: just the bar per side (bar 20 kg)"),
        (
            "/plates 71",
            "71 kg: 25 kg per side (bar 20 kg)\nClosest possible: 70 kg (1 kg short).",
        ),
        ("/plates", "Usage: /plates 102.5"),
        ("/plates heavy", "Usage: /plates 102.5"),
    ],
)
async def test_plates(
    dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi, text: str, expected: str
) -> None:
    assert await say(dispatcher, router, text, 1) == expected


async def test_log_starts_a_workout_and_stores_the_sets(
    dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi
) -> None:
    reply = await say(dispatcher, router, "/log bench 80x5,5,4", 1)
    assert reply == "Logged Bench Press: 80 kg x 5, 5, 4. Workout volume 1,120 kg."
    assert fake.started == 1
    sets = fake.all_sets()
    assert [(s["exercise_id"], s["set_index"], s["reps"]) for s in sets] == [
        (20, 1, 5),
        (20, 2, 5),
        (20, 3, 4),
    ]
    assert {s["client_id"] for s in sets} == {str(client_id(f"tg:{CHAT}:1:{n}")) for n in range(3)}

    # The next /log goes into the same open workout and continues the set numbering.
    await say(dispatcher, router, "/log bench 85x3", 2)
    assert fake.started == 1
    assert sorted(s["set_index"] for s in fake.all_sets()) == [1, 2, 3, 4]


async def test_repeated_log_delivery_stores_one_set_per_set(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi
) -> None:
    """Telegram redelivers an update when the bot died before confirming it. A fresh process
    (no memory of the first delivery) must still store the sets once."""
    first = make_dispatcher(http, MemoryStateStore())
    await first.handle(update("/log squat 100x5x3", 77))
    restarted = make_dispatcher(http, MemoryStateStore())
    await restarted.handle(update("/log squat 100x5x3", 77))
    sets = fake.all_sets()
    assert len(sets) == 3
    assert sorted(s["set_index"] for s in sets) == [1, 2, 3]  # unchanged by the replay
    assert fake.started == 1
    assert fake.put_set_calls == 6  # both deliveries wrote, the second one onto the same rows


async def test_log_bodyweight_and_aliases(
    dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi
) -> None:
    assert await say(dispatcher, router, "/log pullup bw x12x3", 1) == (
        "Logged Pull-Up: bw x 12, 12, 12. Workout volume 0 kg."
    )
    assert await say(dispatcher, router, "/log dl 140x5", 2) == (
        "Logged Deadlift: 140 kg x 5. Workout volume 700 kg."
    )
    assert {s["weight_kg"] for s in fake.all_sets()} == {0.0, 140.0}


async def test_log_ambiguous_exercise_asks_and_a_number_logs(
    dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi, store: MemoryStateStore
) -> None:
    reply = await say(dispatcher, router, "/log press 80x5", 1)
    assert reply.startswith("Which exercise? Reply with a number:\n1. Bench Press\n")
    assert await say(dispatcher, router, "9", 2) == "Reply with a number from 1 to 3."
    assert await say(dispatcher, router, "1", 3) == (
        "Logged Bench Press: 80 kg x 5. Workout volume 400 kg."
    )
    assert [s["client_id"] for s in fake.all_sets()] == [str(client_id(f"tg:{CHAT}:1:0"))]
    assert store.values == {}


async def test_log_unknown_exercise_and_usage(
    dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi
) -> None:
    assert await say(dispatcher, router, "/log zercher 80x5", 1) == (
        'I don\'t know an exercise called "zercher".'
    )
    usage = "Usage: /log bench 80x5x3 (also 80x5,5,4 or bw x12x3)"
    assert await say(dispatcher, router, "/log bench", 2) == usage
    assert await say(dispatcher, router, "/log bench 80x5,5x3", 3) == usage
    assert fake.all_sets() == []


async def test_a_non_number_drops_the_pending_choice(
    dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi, store: MemoryStateStore
) -> None:
    await say(dispatcher, router, "/log press 80x5", 1)
    assert store.values
    reply = await say(dispatcher, router, "never mind", 2)
    assert reply.startswith("I only understand commands for now.")
    assert store.values == {}


async def test_done_finishes_with_volume_and_records(
    dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi
) -> None:
    assert await say(dispatcher, router, "/done", 1) == "No open workout today."
    await say(dispatcher, router, "/log bench 82.5x5x2", 2)
    reply = await say(dispatcher, router, "/done", 3)
    assert reply == (
        "Workout done: 2 sets · 1 exercises · 825 kg · 0m 00s\n"
        "New records:\n"
        "🏆 Bench Press: 82.5 kg x 5"
    )
    assert await say(dispatcher, router, "/done", 4) == "No open workout today."


async def test_api_errors_on_writes_get_the_friendly_reply(
    dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi
) -> None:
    router["put_set"].mock(return_value=httpx.Response(503))
    reply = await say(dispatcher, router, "/log bench 80x5", 1)
    assert reply == "Sorry, I can't reach the trainsync API right now. Try again in a minute."


# ---------------------------------------------------------------- nutrition


async def test_eat_logs_a_clear_match(
    dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi
) -> None:
    reply = await say(dispatcher, router, "/eat oats 60", 5)
    assert reply == "Logged 60 g Rolled oats (dinner): 223 kcal."
    [entry] = fake.food_log.values()
    assert entry["client_id"] == str(client_id(f"tg:{CHAT}:5:eat"))
    assert (entry["date"], entry["meal"], entry["grams"]) == ("2026-10-18", "dinner", 60.0)
    # A redelivered update writes the same entry again, not a second one.
    await say(dispatcher, router, "/eat oats 60", 5)
    assert len(fake.food_log) == 1


async def test_eat_ambiguous_asks_and_a_number_logs(
    dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi
) -> None:
    reply = await say(dispatcher, router, "/eat greek 150", 1)
    assert reply == ("Which one? Reply with a number:\n1. Greek yogurt (Acme)\n2. Greek yogurt 0%")
    assert fake.food_log == {}
    assert await say(dispatcher, router, "3", 2) == "Reply with a number from 1 to 2."
    assert await say(dispatcher, router, "2", 3) == (
        "Logged 150 g Greek yogurt 0% (dinner): 86 kcal."
    )
    [entry] = fake.food_log.values()
    assert entry["client_id"] == str(client_id(f"tg:{CHAT}:1:eat"))


async def test_eat_exact_name_wins_and_unknown_food(
    dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi
) -> None:
    assert await say(dispatcher, router, "/eat greek yogurt 100", 1) == (
        "Logged 100 g Greek yogurt (Acme) (dinner): 97 kcal."
    )
    assert await say(dispatcher, router, "/eat durian 100", 2) == (
        'No food matches "durian". Add it on the web, then try again.'
    )
    assert router["lookup"].called
    assert await say(dispatcher, router, "/eat oats", 3) == (
        "Usage: /eat <food> <grams>, e.g. /eat oats 60"
    )


async def test_kcal(dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi) -> None:
    assert await say(dispatcher, router, "/kcal", 1) == "Food today (18 Oct)\nNothing logged yet."
    await say(dispatcher, router, "/eat oats 60", 2)
    assert await say(dispatcher, router, "/kcal", 3) == (
        "Food today (18 Oct)\n"
        "223 kcal of 2600 kcal · 2377 kcal left · 1 entries\n"
        "Protein 32 g · carbs 120 g · F 20 g"
    )
    fake.kcal_target = None
    await say(dispatcher, router, "/eat oats 40", 4)
    reply = await say(dispatcher, router, "/kcal", 5)
    assert "372 kcal · 2 entries" in reply
    assert reply.endswith("Some foods have unknown macros; they are left out.")
    assert router["nutrition_summary"].calls.last.request.url.params["date"] == "2026-10-18"


async def test_weight(dispatcher: Dispatcher, router: respx.MockRouter, fake: FakeApi) -> None:
    assert await say(dispatcher, router, "/weight 78,4", 1) == "Saved for 18 Oct: 78.4 kg."
    assert fake.body_metrics == {"2026-10-18": 78.4}
    assert await say(dispatcher, router, "/weight", 2) == "Usage: /weight 78.4"
    assert await say(dispatcher, router, "/weight 0", 3) == "Usage: /weight 78.4"


async def test_local_day_after_midnight(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi, store: MemoryStateStore
) -> None:
    """22:30 UTC is already the next day in Istanbul: food and the scale go to that day."""
    late = datetime(2026, 10, 18, 22, 30, tzinfo=UTC)
    api = ReadApi(http, API, SecretStr("k"))
    nutrition = NutritionCommands(api, store, lambda: late, ZONE, MSG)
    telegram = TelegramApi(http, SecretStr(BOT_TOKEN), base_url=TELEGRAM)
    dispatcher = Dispatcher(
        telegram, Commands(api, lambda: late, MSG), {CHAT}, MSG, features=[nutrition]
    )
    await dispatcher.handle(update("/weight 78", 1))
    await dispatcher.handle(update("/eat oats 50", 2))
    assert list(fake.body_metrics) == ["2026-10-19"]
    assert [e["date"] for e in fake.food_log.values()] == ["2026-10-19"]
    assert [e["meal"] for e in fake.food_log.values()] == ["snack"]  # 01:30 local


@pytest.mark.parametrize("lang", ["en", "tr"])
async def test_nutrition_and_scale_replies_are_neutral_in_hardcore(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi, lang: str
) -> None:
    """BOT_TONE=hardcore changes nothing about food or the scale."""
    texts: dict[str, list[str]] = {}
    for tone in ("neutral", "hardcore"):
        fake.food_log.clear()
        before = len(replies(router))
        msg = Messages(PACKS[tone, lang], random.Random(1))  # type: ignore[index]
        dispatcher = make_dispatcher(http, MemoryStateStore(), msg)
        for n, text in enumerate(
            ["/eat oats 60", "/eat greek 100", "1", "/kcal", "/weight 78.4", "/weight x", "/eat"]
        ):
            await dispatcher.handle(update(text, 100 + n))
        texts[tone] = replies(router)[before:]
    assert texts["hardcore"] == texts["neutral"]
    assert len(texts["neutral"]) == 7
