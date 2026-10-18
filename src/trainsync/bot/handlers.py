"""Command handlers and update dispatch.

Commands are deterministic: each one maps to fixed API calls and a formatting function.
Training, nutrition and check-in commands live in their own `Feature`s (P6.8, P6.9). Plain text
that no feature claims goes to the optional assistant (P5.7).
"""

from collections.abc import Awaitable, Callable, Sequence
from datetime import date, timedelta

from trainsync.bot import formatting
from trainsync.bot.common import Feature, Incoming, Press, PressResult, Reply
from trainsync.bot.messages import Key, Messages
from trainsync.bot.read_api import ReadApi, ReadApiError
from trainsync.bot.telegram import (
    CallbackQuery,
    TelegramApi,
    TelegramError,
    TelegramUnavailableError,
    Update,
)
from trainsync.core.clock import Clock
from trainsync.core.logging import get_logger
from trainsync.core.metrics import BOT_UPDATES
from trainsync.db.repositories.reads import week_start

log = get_logger(__name__)

COMMANDS = frozenset({"start", "help", "week", "last", "stats", "status"})
PERIODS = {"4w": 4, "12w": 12, "52w": 52}
DEFAULT_PERIOD = "4w"
_SPORT_ALIASES = {
    "run": "Run",
    "trailrun": "TrailRun",
    "ride": "Ride",
    "bike": "Ride",
    "gravelride": "GravelRide",
    "virtualride": "VirtualRide",
    "swim": "Swim",
    "walk": "Walk",
    "hike": "Hike",
}
# (chat_id, text) → reply; the assistant plugs in here (P5.7).
TextHandler = Callable[[int, str], Awaitable[str]]


class UsageError(Exception):
    """Bad command arguments; the dispatcher shows the usage message for `key`."""

    def __init__(self, key: Key) -> None:
        super().__init__(key)
        self.key = key


def parse_command(text: str) -> tuple[str | None, list[str]]:
    """`/stats@my_bot 12w Run` → ("stats", ["12w", "Run"]); plain text → (None, [])."""
    text = text.strip()
    if not text.startswith("/"):
        return None, []
    head, *args = text.split()
    return head[1:].split("@", 1)[0].lower(), args


def parse_stats_args(args: list[str]) -> tuple[str, str | None]:
    """`[4w|12w|52w] [sport]` in either order → (period, sport_type)."""
    period, sport = DEFAULT_PERIOD, None
    for arg in args:
        if arg.lower() in PERIODS:
            period = arg.lower()
        elif sport is None:
            sport = _SPORT_ALIASES.get(arg.lower(), arg[:1].upper() + arg[1:])
        else:
            raise UsageError(Key.USAGE_STATS)
    return period, sport


def week_ranges(today: date) -> tuple[tuple[date, date], tuple[date, date]]:
    """(this ISO week so far, the whole previous ISO week)."""
    monday = week_start(today)
    return (monday, today), (monday - timedelta(days=7), monday - timedelta(days=1))


def period_range(today: date, weeks: int) -> tuple[date, date]:
    """The last `weeks` ISO weeks, the current (partial) one included."""
    return week_start(today) - timedelta(weeks=weeks - 1), today


class Commands:
    def __init__(self, api: ReadApi, clock: Clock, msg: Messages) -> None:
        self._api = api
        self._clock = clock
        self._msg = msg

    async def run(self, command: str, args: list[str]) -> str:
        if command == "week":
            return await self.week()
        if command == "last":
            return await self.last()
        if command == "stats":
            return await self.stats(args)
        if command == "status":
            return await self.status()
        return self._msg.help()  # start, help

    async def week(self) -> str:
        now = self._clock()
        (this_from, this_to), (last_from, last_to) = week_ranges(now.date())
        this_week = await self._api.summary(this_from, this_to)
        last_week = await self._api.summary(last_from, last_to)
        return formatting.format_week(this_week, last_week, now, self._msg)

    async def last(self) -> str:
        page = await self._api.activities(limit=1)
        latest = page.items[0] if page.items else None
        return formatting.format_last(latest, page.last_synced_at, self._clock(), self._msg)

    async def stats(self, args: list[str]) -> str:
        period, sport = parse_stats_args(args)
        now = self._clock()
        start, end = period_range(now.date(), PERIODS[period])
        summary = await self._api.summary(start, end, sport)
        weekly = await self._api.weekly(start, end, sport)
        return formatting.format_stats(summary, weekly.weeks, period, now, self._msg)

    async def status(self) -> str:
        return formatting.format_status(await self._api.sync_status(), self._clock(), self._msg)


class Dispatcher:
    """One update in, at most one reply out. Chats outside the allowlist get nothing.

    `features` (training, nutrition, check-in) add commands, take plain-text answers to their own
    questions (a pending numbered choice, a check-in step) and handle button presses. Plain text
    nobody claims goes to the assistant.
    """

    def __init__(
        self,
        telegram: TelegramApi,
        commands: Commands,
        allowed_chat_ids: set[int],
        msg: Messages,
        text_handler: TextHandler | None = None,
        *,
        features: Sequence[Feature] = (),
    ) -> None:
        self._telegram = telegram
        self._commands = commands
        self._msg = msg
        self._allowed = allowed_chat_ids
        self._text_handler = text_handler
        self._features = tuple(features)
        self._known = COMMANDS.union(*(f.commands for f in self._features))

    async def handle(self, update: Update) -> None:
        if update.callback_query is not None:
            await self._handle_press(update.update_id, update.callback_query)
            return
        message = update.message
        if message is None or not message.text:
            BOT_UPDATES.labels("none", "ignored").inc()
            return
        chat_id = message.chat.id
        command, args = parse_command(message.text)
        label = self._label(command)
        if chat_id not in self._allowed:
            log.info("bot_chat_denied", chat_id=chat_id, command=label)
            BOT_UPDATES.labels(label, "denied").inc()
            return
        incoming = Incoming(chat_id, update.update_id, message.text)
        reply, outcome = await self._reply(incoming, command, args)
        outcome = await self._send(chat_id, reply, label, outcome)
        log.info("bot_update", chat_id=chat_id, command=label, outcome=outcome)
        BOT_UPDATES.labels(label, outcome).inc()

    async def _send(self, chat_id: int, reply: Reply, label: str, outcome: str) -> str:
        if not reply.text:
            return "duplicate"  # a feature recognised a redelivered update: nothing to say
        try:
            await self._telegram.send_message(chat_id, reply.text, reply.keyboard)
        except (TelegramError, TelegramUnavailableError) as exc:
            log.warning("bot_reply_failed", chat_id=chat_id, command=label, error=str(exc))
            return "send_failed"
        return outcome

    async def _reply(
        self, incoming: Incoming, command: str | None, args: list[str]
    ) -> tuple[Reply, str]:
        msg = self._msg
        try:
            if command is None:
                for feature in self._features:
                    claimed = await feature.text(incoming)
                    if claimed is not None:
                        return claimed, "ok"
                if self._text_handler is None:
                    return Reply(msg(Key.NO_ASSISTANT, help=msg.help())), "ok"
                return Reply(await self._text_handler(incoming.chat_id, incoming.text)), "ok"
            for feature in self._features:
                if command in feature.commands:
                    return await feature.command(incoming, command, args), "ok"
            if command not in COMMANDS:
                unknown = msg(Key.UNKNOWN_COMMAND, command=command, help=msg.help())
                return Reply(unknown), "unknown"
            return Reply(await self._commands.run(command, args)), "ok"
        except UsageError as exc:
            return Reply(msg(exc.key)), "usage"
        except ReadApiError as exc:
            log.warning("bot_read_api_failed", chat_id=incoming.chat_id, error=str(exc))
            return Reply(msg(Key.API_DOWN)), "error"

    async def _handle_press(self, update_id: int, query: CallbackQuery) -> None:
        message = query.message
        chat_id = message.chat.id if message is not None else None
        if chat_id is None or chat_id not in self._allowed:
            log.info("bot_chat_denied", chat_id=chat_id, command="button")
            BOT_UPDATES.labels("button", "denied").inc()
            return
        press = Press(chat_id, update_id, query.data or "", message.message_id if message else None)
        result, outcome = await self._press_result(press)
        try:
            await self._telegram.answer_callback_query(query.id, result.toast)
            if result.accepted and press.message_id is not None:
                await self._telegram.remove_keyboard(chat_id, press.message_id)
        except (TelegramError, TelegramUnavailableError) as exc:
            # Not fatal: the spinner times out by itself, old buttons are rejected as stale.
            log.info("bot_button_ack_failed", chat_id=chat_id, error=str(exc))
        if result.reply is not None:
            outcome = await self._send(chat_id, result.reply, "button", outcome)
        log.info("bot_update", chat_id=chat_id, command="button", outcome=outcome)
        BOT_UPDATES.labels("button", outcome).inc()

    async def _press_result(self, press: Press) -> tuple[PressResult, str]:
        try:
            for feature in self._features:
                result = await feature.press(press)
                if result is not None:
                    return result, "ok" if result.accepted else "stale"
        except ReadApiError as exc:
            log.warning("bot_read_api_failed", chat_id=press.chat_id, error=str(exc))
            return PressResult(reply=Reply(self._msg(Key.API_DOWN))), "error"
        return PressResult(toast=self._msg(Key.CHECKIN_STALE)), "stale"

    def _label(self, command: str | None) -> str:
        """Bounded metric label: a known command, `text`, or `unknown`."""
        if command is None:
            return "text"
        return command if command in self._known else "unknown"
