"""P6.9: every path of the check-in conversation, against the fake Telegram API and the stubbed
trainsync API (both respx), with the state store in memory."""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

import json
import random
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from pydantic import SecretStr

from tests.support.bot_api import API, FakeApi, install, planned
from tests.support.messages import NEUTRAL_EN as MSG
from tests.support.state import MemoryStateStore
from tests.support.swears import swears
from tests.support.telegram import BOT_TOKEN, BOT_URL, TELEGRAM, message_update, ok, sent_messages
from trainsync.bot.checkin import (
    MINUS,
    STATE_TTL_S,
    CheckinFlow,
    prompt,
    set_id,
    state_key,
    workout_client_id,
)
from trainsync.bot.handlers import Commands, Dispatcher
from trainsync.bot.messages import PACKS, Key, Messages, NeutralKey
from trainsync.bot.read_api import ReadApi
from trainsync.bot.telegram import TelegramApi, Update
from trainsync.bot.training import TrainingCommands
from trainsync.coach.categories import Category
from trainsync.coach.lines import SAVAGE_MAX, MemoryRecentStore, load_pack
from trainsync.coach.mode import CoachMode, MemorySoftModeStore
from trainsync.coach.savage_tr import LINES
from trainsync.coach.voice import CoachVoice
from trainsync.core.settings import BotProfanity

NOW = datetime(2026, 10, 18, 18, 5, tzinfo=UTC)  # 21:05 in Istanbul
DAY = "2026-10-18"
ZONE = ZoneInfo("Europe/Istanbul")
CHAT = 42


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{BOT_URL}/sendMessage", name="send").mock(return_value=ok({}))
        mock.post(f"{BOT_URL}/answerCallbackQuery", name="answer").mock(return_value=ok(True))
        mock.post(f"{BOT_URL}/editMessageReplyMarkup", name="edit").mock(return_value=ok(True))
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


class Chat:
    """Drives the dispatcher like a Telegram user: types, taps buttons by their label."""

    def __init__(self, dispatcher: Dispatcher, router: respx.MockRouter) -> None:
        self.dispatcher = dispatcher
        self.router = router
        self.update_id = 1000

    def _next(self) -> int:
        self.update_id += 1
        return self.update_id

    async def say(self, text: str, update_id: int | None = None) -> str:
        await self.dispatcher.handle(
            Update.model_validate(message_update(update_id or self._next(), CHAT, text))
        )
        return self.last["text"]

    async def press_data(self, data: str, update_id: int | None = None) -> None:
        update = {
            "update_id": update_id or self._next(),
            "callback_query": {
                "id": f"cq-{self.update_id}",
                "data": data,
                "message": {"message_id": 7, "chat": {"id": CHAT}},
            },
        }
        await self.dispatcher.handle(Update.model_validate(update))

    async def tap(self, label: str) -> str:
        await self.press_data(self.button(label))
        return self.last["text"]

    @property
    def sent(self) -> list[dict[str, Any]]:
        return sent_messages(self.router["send"])

    @property
    def last(self) -> dict[str, Any]:
        return self.sent[-1]

    def labels(self) -> list[str]:
        markup = self.last.get("reply_markup", {"inline_keyboard": []})
        return [b["text"] for row in markup["inline_keyboard"] for b in row]

    def button(self, label: str, message: dict[str, Any] | None = None) -> str:
        markup = (message or self.last)["reply_markup"]
        for row in markup["inline_keyboard"]:
            for b in row:
                if b["text"] == label:
                    data: str = b["callback_data"]
                    return data
        raise AssertionError(f"no button {label!r} in {markup}")

    def toasts(self) -> list[str]:
        bodies = [json.loads(c.request.content) for c in self.router["answer"].calls]
        return [b.get("text", "") for b in bodies]


def make_chat(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    store: MemoryStateStore,
    msg: Messages = MSG,
    voice: CoachVoice | None = None,
) -> Chat:
    telegram = TelegramApi(http, SecretStr(BOT_TOKEN), base_url=TELEGRAM)
    api = ReadApi(http, API, SecretStr("bot-key"))
    clock = lambda: NOW  # noqa: E731
    dispatcher = Dispatcher(
        telegram,
        Commands(api, clock, msg),
        {CHAT},
        msg,
        features=[
            CheckinFlow(api, store, clock, ZONE, msg, voice),
            TrainingCommands(api, store, clock, ZONE, msg),
        ],
        voice=voice,
    )
    return Chat(dispatcher, router)


@pytest.fixture
def chat(http: httpx.AsyncClient, router: respx.MockRouter, store: MemoryStateStore) -> Chat:
    return make_chat(http, router, store)


def with_program(fake: FakeApi) -> None:
    fake.with_program(
        11, planned(20, 3, 5, 5, 80.0), planned(1, 3, 5, 8, 100.0), planned(38, 3, 8, 8, None)
    )


def sets_of(fake: FakeApi, exercise_id: int) -> list[tuple[int, float, int]]:
    rows = [s for s in fake.all_sets() if s["exercise_id"] == exercise_id]
    return sorted((s["set_index"], s["weight_kg"], s["reps"]) for s in rows)


# ---------------------------------------------------------------- done with a program


async def test_done_with_program_walks_the_plan(chat: Chat, fake: FakeApi) -> None:
    with_program(fake)
    reply = await chat.say("/report")
    assert reply == "Daily check-in: did you train today?"
    assert chat.labels() == ["✅ Done", "🟡 Partly", "❌ Skipped", "😴 Rest day", "🤕 Sick/injured"]

    reply = await chat.tap("✅ Done")
    assert fake.checkins[DAY]["status"] == "done"  # stored at once: no reminder after this
    assert fake.started == 1
    # Started under the day's deterministic id: a retry or an edit reuses this workout.
    day = date.fromisoformat(DAY)
    assert [w.client_id for w in fake.workouts.values()] == [str(workout_client_id(day))]
    assert reply == (
        "1/3 Bench Press\nPlan: 3 x 5 · 80 kg\nTap a button or type 80x5x3, 80x5,5,4 or bw x12x3."
    )
    assert chat.labels() == ["As planned", "+2.5 kg", f"{MINUS}2.5 kg", "Skip exercise"]

    reply = await chat.tap("As planned")
    assert reply.startswith("Saved Bench Press: 80 kg x 5, 5, 5.\n2/3 Back Squat")
    assert sets_of(fake, 20) == [(1, 80.0, 5), (2, 80.0, 5), (3, 80.0, 5)]
    assert {s["client_id"] for s in fake.all_sets()} == {
        str(set_id(datetime(2026, 10, 18).date(), 20, i)) for i in (1, 2, 3)
    }

    reply = await chat.say("100x5,5,4")
    assert reply.startswith("Saved Back Squat: 100 kg x 5, 5, 4.\n3/3 Pull-Up\nPlan: 3 x 8 · bw")
    assert sets_of(fake, 1) == [(1, 100.0, 5), (2, 100.0, 5), (3, 100.0, 4)]

    reply = await chat.tap("Skip exercise")
    assert reply == "Skipped Pull-Up.\nScale reading today? Reply like 78.4, or tap Skip."
    assert await chat.say("78,4") == "Hours of sleep last night? Reply like 7.5, or tap Skip."
    assert await chat.say("7.5") == "Energy today, from 1 (low) to 5 (high)?"
    assert chat.labels() == ["1", "2", "3", "4", "5", "Skip"]
    fake.streak = 6
    summary = await chat.tap("4")
    assert summary == (
        "Check-in saved for 18 Oct: ✅ Done\n"
        "Workout: 6 sets · 2,600 kg\n"
        "Scale: 78.4 kg\n"
        "Sleep: 7.5 h\n"
        "Energy: 4/5\n"
        "Check-in streak: 6 days"
    )
    assert chat.labels() == ["✏️ Edit"]
    checkin = fake.checkins[DAY]
    assert (checkin["status"], checkin["workout_id"], checkin["energy_1_5"]) == ("done", 100, 4)
    assert (checkin["sleep_hours"], checkin["body_weight_kg"]) == ("7.5", "78.4")
    assert fake.body_metrics == {DAY: 78.4}
    assert router_calls(chat, "edit") >= 1  # answered questions lose their buttons


def router_calls(chat: Chat, name: str) -> int:
    return chat.router[name].call_count


@pytest.mark.parametrize(
    ("label", "weight"), [("+2.5 kg", 82.5), (f"{MINUS}2.5 kg", 77.5), ("As planned", 80.0)]
)
async def test_plus_minus_and_as_planned_produce_the_right_sets(
    chat: Chat, fake: FakeApi, label: str, weight: float
) -> None:
    with_program(fake)
    await chat.say("/report")
    await chat.tap("✅ Done")
    await chat.tap(label)
    assert sets_of(fake, 20) == [(i, weight, 5) for i in (1, 2, 3)]


async def test_partly_then_records_in_the_summary(chat: Chat, fake: FakeApi) -> None:
    with_program(fake)
    await chat.say("/report")
    await chat.tap("🟡 Partly")
    await chat.tap("+2.5 kg")  # 82.5 kg: the stub reports a weight-for-reps record
    await chat.tap("Skip exercise")
    await chat.tap("Skip exercise")
    for _ in range(3):
        await chat.tap("Skip")
    summary = chat.last["text"]
    assert summary.startswith("Check-in saved for 18 Oct: 🟡 Partly\nWorkout: 3 sets · 1,238 kg")
    assert "New records:\n🏆 Bench Press: 82.5 kg x 5" in summary
    checkin = fake.checkins[DAY]
    assert (checkin["status"], checkin["sleep_hours"], checkin["body_weight_kg"]) == (
        "partial",
        None,
        None,
    )


async def test_exercises_logged_earlier_today_are_not_asked_again(
    chat: Chat, fake: FakeApi
) -> None:
    with_program(fake)
    await chat.say("/log bench 85x3x3")  # from the gym, before the check-in
    await chat.say("/report")
    reply = await chat.tap("✅ Done")
    assert reply.startswith("Bench Press: already logged today (85 kg x 3, 3, 3).\n2/3 Back Squat")
    assert fake.started == 1  # the open workout from /log is reused


async def test_invalid_input_re_prompts(chat: Chat, fake: FakeApi, store: MemoryStateStore) -> None:
    with_program(fake)
    await chat.say("/report")
    await chat.tap("✅ Done")
    reply = await chat.say("heavy")
    assert reply == "I couldn't read that. Type 80x5x3, 80x5,5,4 or bw x12x3, or tap a button."
    assert "As planned" in chat.labels()  # same question, still answerable
    assert fake.all_sets() == []
    await chat.tap("As planned")
    await chat.tap("Skip exercise")
    await chat.tap("Skip exercise")
    assert await chat.say("abc") == "Please reply with a number like 78.4, or tap Skip."
    assert await chat.say("1000") == "Please reply with a number like 78.4, or tap Skip."
    await chat.tap("Skip")
    assert await chat.say("25") == "Please reply with a number like 7.5, or tap Skip."
    await chat.say("8")
    assert await chat.say("7") == "Please reply with a number like 4, or tap Skip."
    reply = await chat.say("5")
    assert reply.startswith("Check-in saved for 18 Oct: ✅ Done")
    assert fake.checkins[DAY]["energy_1_5"] == 5
    assert store.ttls[state_key(CHAT, datetime(2026, 10, 18).date())] == STATE_TTL_S


# ---------------------------------------------------------------- done without a program


async def test_done_without_program_takes_log_lines(chat: Chat, fake: FakeApi) -> None:
    await chat.say("rapor")
    reply = await chat.tap("✅ Done")
    assert reply.startswith("What did you do? One exercise per message, like /log")
    assert chat.labels() == ["Finish"]
    assert fake.started == 0  # nothing to store yet

    assert await chat.say("bench 80x5x3") == "Saved Bench Press: 80 kg x 5, 5, 5."
    assert await chat.say("bench 85x3") == "Saved Bench Press: 85 kg x 3."
    assert sets_of(fake, 20) == [(1, 80.0, 5), (2, 80.0, 5), (3, 80.0, 5), (4, 85.0, 3)]

    reply = await chat.say("press 50x5")
    assert reply.startswith("Which exercise? Reply with a number:\n1. Bench Press")
    assert await chat.say("7") == "Reply with a number from 1 to 3."
    assert await chat.say("2") == "Saved Incline Bench Press: 50 kg x 5."

    assert await chat.say("zercher 60x5") == 'I don\'t know an exercise called "zercher".'
    assert await chat.say("I did stuff") == (
        "I couldn't read that. Type 80x5x3, 80x5,5,4 or bw x12x3, or tap a button."
    )
    reply = await chat.say("done")
    assert reply == "Scale reading today? Reply like 78.4, or tap Skip."
    for _ in range(3):
        await chat.tap("Skip")
    assert chat.last["text"].startswith("Check-in saved for 18 Oct: ✅ Done\nWorkout: 5 sets")
    assert fake.checkins[DAY]["workout_id"] == 100


async def test_done_without_program_and_nothing_logged(chat: Chat, fake: FakeApi) -> None:
    await chat.say("/report")
    await chat.tap("✅ Done")
    await chat.tap("Finish")
    for _ in range(3):
        await chat.tap("Skip")
    assert chat.last["text"] == ("Check-in saved for 18 Oct: ✅ Done\nCheck-in streak: 0 days")
    assert fake.checkins[DAY]["workout_id"] is None


# ---------------------------------------------------------------- skipped, rest, sick


async def test_skipped_with_a_reason(chat: Chat, fake: FakeApi) -> None:
    await chat.say("/report")
    reply = await chat.tap("❌ Skipped")
    assert reply == "What got in the way? A few words, or tap Skip."
    reply = await chat.say("late meeting")
    assert reply == "Noted, thanks.\nScale reading today? Reply like 78.4, or tap Skip."
    for _ in range(3):
        await chat.tap("Skip")
    checkin = fake.checkins[DAY]
    assert (checkin["status"], checkin["reason_note"]) == ("skipped", "late meeting")
    assert fake.started == 0


async def test_skipped_without_a_reason(chat: Chat, fake: FakeApi) -> None:
    await chat.say("/report")
    await chat.tap("❌ Skipped")
    reply = await chat.tap("Skip")
    assert reply == "Noted.\nScale reading today? Reply like 78.4, or tap Skip."
    assert fake.checkins[DAY]["reason_note"] is None


async def test_hardcore_pushes_only_on_a_skip_without_reason(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi
) -> None:
    pack = PACKS["hardcore", "en"]
    chat = make_chat(http, router, MemoryStateStore(), Messages(pack, random.Random(3)))
    await chat.say("/report")
    await chat.tap("❌ Skipped")
    reply = await chat.tap("Skip")
    first_line = reply.splitlines()[0]
    assert first_line in pack.texts[Key.CHECKIN_SKIPPED_NO_REASON]
    assert first_line != PACKS["neutral", "en"].texts[Key.CHECKIN_SKIPPED_NO_REASON][0]


def savage_voice(msg: Messages, profanity: BotProfanity = "roast") -> CoachVoice:
    return CoachVoice(
        msg=msg,
        mode=CoachMode(configured=True, soft=MemorySoftModeStore()),
        pack=load_pack(None),
        recent=MemoryRecentStore(),
        rng=random.Random(2),
        profanity=profanity,
    )


async def test_savage_roasts_a_skip_without_a_reason(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi
) -> None:
    msg = Messages(PACKS["hardcore", "tr"], random.Random(3))
    chat = make_chat(http, router, MemoryStateStore(), msg, savage_voice(msg))
    await chat.say("/report")
    await chat.tap("❌ Atladım")
    reply = await chat.tap("Geç")
    assert any(reply.startswith(line) for line in LINES[Category.MISSED_WORKOUT]), reply


async def test_savage_roasts_an_excuse_given_as_the_reason(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi
) -> None:
    msg = Messages(PACKS["hardcore", "tr"], random.Random(3))
    chat = make_chat(http, router, MemoryStateStore(), msg, savage_voice(msg))
    await chat.say("/report")
    await chat.tap("❌ Atladım")
    reply = await chat.say("canım istemedi")
    assert any(reply.startswith(line) for line in LINES[Category.EXCUSE]), reply


async def test_a_pain_reason_is_never_roasted_even_in_savage(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi
) -> None:
    msg = Messages(PACKS["hardcore", "tr"], random.Random(3))
    chat = make_chat(http, router, MemoryStateStore(), msg, savage_voice(msg))
    await chat.say("/report")
    await chat.tap("❌ Atladım")
    reply = await chat.say("dizim ağrıyor, canım istemedi")
    assert reply.startswith(msg(Key.CHECKIN_SICK_SAVED))
    assert msg.neutral(NeutralKey.SAFETY_PAIN) in reply
    assert not any(line in reply for lines in LINES.values() for line in lines)


@pytest.mark.parametrize(
    ("label", "status", "line"),
    [
        ("😴 Rest day", "rest", "Rest day noted. Recovery is part of training."),
        ("🤕 Sick/injured", "sick_or_injured", "Noted. Take care of yourself; training can wait."),
    ],
)
async def test_rest_and_sick_are_just_stored(
    chat: Chat, fake: FakeApi, label: str, status: str, line: str
) -> None:
    await chat.say("/report")
    reply = await chat.tap(label)
    assert reply == f"{line}\nScale reading today? Reply like 78.4, or tap Skip."
    assert fake.checkins[DAY]["status"] == status
    assert fake.started == 0
    for _ in range(3):
        await chat.tap("Skip")
    assert chat.last["text"].startswith(f"Check-in saved for 18 Oct: {label}")


@pytest.mark.parametrize("lang", ["en", "tr"])
async def test_rest_and_sick_are_calm_in_hardcore_too(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi, lang: str
) -> None:
    pack = PACKS["hardcore", lang]  # type: ignore[index]
    for label_key, key in (
        (Key.CHECKIN_BTN_REST, Key.CHECKIN_REST_SAVED),
        (Key.CHECKIN_BTN_SICK, Key.CHECKIN_SICK_SAVED),
    ):
        chat = make_chat(http, router, MemoryStateStore(), Messages(pack, random.Random(1)))
        await chat.say("/report")
        reply = await chat.tap(pack.texts[label_key][0])
        assert reply.splitlines()[0] == pack.texts[key][0]


# ---------------------------------------------------------------- stale buttons and duplicates


async def test_stale_and_double_tapped_buttons_are_rejected_politely(
    chat: Chat, fake: FakeApi
) -> None:
    with_program(fake)
    await chat.say("/report")
    question = chat.last
    await chat.tap("✅ Done")
    sent_before = len(chat.sent)
    await chat.press_data(chat.button("❌ Skipped", question))  # an older message's button
    await chat.press_data(chat.button("✅ Done", question))  # a double tap
    assert len(chat.sent) == sent_before  # no new message, no new question
    assert chat.toasts()[-2:] == [MSG(Key.CHECKIN_STALE)] * 2
    assert fake.checkins[DAY]["status"] == "done"
    assert fake.started == 1
    # Yesterday's button, and something that is not a check-in button at all.
    await chat.press_data("ci:20261017:3:s:rest")
    await chat.press_data("other:thing")
    assert chat.toasts()[-2:] == [MSG(Key.CHECKIN_STALE)] * 2


async def test_redelivered_press_and_message_store_nothing_twice(chat: Chat, fake: FakeApi) -> None:
    with_program(fake)
    await chat.say("/report")
    await chat.tap("✅ Done")
    data = chat.button("As planned")
    await chat.press_data(data, update_id=5000)
    await chat.press_data(data, update_id=5000)  # the same update again
    assert len(sets_of(fake, 20)) == 3
    puts = fake.put_set_calls
    sent = len(chat.sent)
    await chat.say("100x5x3", update_id=5001)
    await chat.say("100x5x3", update_id=5001)  # redelivered: ignored, no reply
    assert len(chat.sent) == sent + 1
    assert fake.put_set_calls == puts + 3
    assert len(sets_of(fake, 1)) == 3
    assert chat.last["text"].startswith("Saved Back Squat")


async def test_edit_reopens_the_flow_and_overwrites(chat: Chat, fake: FakeApi) -> None:
    with_program(fake)
    await chat.say("/report")
    await chat.tap("✅ Done")
    await chat.tap("As planned")
    await chat.tap("Skip exercise")
    await chat.tap("Skip exercise")
    for _ in range(3):
        await chat.tap("Skip")
    summary = chat.last
    assert await chat.tap("✏️ Edit") == "Daily check-in: did you train today?"
    await chat.press_data(chat.button("✏️ Edit", summary))  # the old Edit button is stale now
    assert chat.toasts()[-1] == MSG(Key.CHECKIN_STALE)
    reply = await chat.tap("✅ Done")
    assert reply.startswith("1/3 Bench Press")  # our own sets: asked again, not "already logged"
    await chat.tap("+2.5 kg")
    assert sets_of(fake, 20) == [(i, 82.5, 5) for i in (1, 2, 3)]  # overwritten, not added
    assert fake.started == 1


async def test_the_workers_prompt_is_answerable_without_state(
    chat: Chat, fake: FakeApi, router: respx.MockRouter
) -> None:
    """The worker sends the prompt with seq 0; the bot has no state for the day yet."""
    reply = prompt(MSG, datetime(2026, 10, 18).date())
    message = {
        "reply_markup": {
            "inline_keyboard": [
                [{"text": b.text, "callback_data": b.data} for b in row]
                for row in reply.keyboard or ()
            ]
        }
    }
    await chat.press_data(chat.button("😴 Rest day", message))
    assert chat.last["text"].startswith("Rest day noted.")
    assert fake.checkins[DAY]["status"] == "rest"
    reminder = prompt(MSG, datetime(2026, 10, 18).date(), reminder=True)
    assert reminder.text.startswith("Reminder: today's check-in is still open.")


async def test_plain_text_outside_the_flow_is_not_taken(chat: Chat, fake: FakeApi) -> None:
    reply = await chat.say("hello")
    assert reply.startswith("I only understand commands for now.")


async def test_api_down_on_a_press(chat: Chat, fake: FakeApi, router: respx.MockRouter) -> None:
    await chat.say("/report")
    router["put_checkin"].mock(return_value=httpx.Response(503))
    reply = await chat.tap("😴 Rest day")
    assert reply == MSG(Key.API_DOWN)


async def test_in_max_the_check_in_questions_swear_but_calm_answers_never_do(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi
) -> None:
    """ADR 0032: max reaches the check-in prompt; pain and distress replies stay clean."""
    msg = Messages(PACKS["hardcore", "tr"], random.Random(3))
    chat = make_chat(http, router, MemoryStateStore(), msg, savage_voice(msg, "max"))
    openers = SAVAGE_MAX["tr"][Category.MAX_OPENER]
    prompt = await chat.say("/report")
    assert prompt.split("\n", 1)[0] in openers, prompt
    await chat.tap("❌ Atladım")
    calm = await chat.say("bugün hiçbir şey yemedim, kendimden nefret ediyorum")
    assert msg.neutral(NeutralKey.SAFETY_DISTRESS) in calm
    assert not swears(calm), calm
    second = make_chat(http, router, MemoryStateStore(), msg, savage_voice(msg, "max"))
    await second.say("/report")
    await second.tap("❌ Atladım")
    pain = await second.say("dizim ağrıyor")
    assert msg.neutral(NeutralKey.SAFETY_PAIN) in pain
    assert not swears(pain), pain
