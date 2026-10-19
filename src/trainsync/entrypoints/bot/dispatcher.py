"""Command handlers and update dispatch.

Commands are deterministic: each one maps to fixed API calls and a formatting function.
Training, nutrition and check-in commands live in their own `Feature`s (P6.8, P6.9). Plain text
that no feature claims goes to the optional assistant (P5.7).

Only linked chats are served (ADR 0036): an unknown chat gets the link hint and nothing else,
`/link CODE` binds it, `/unlink` unbinds it. A linked chat's update runs in its user's voice and
every API call acts as that user.
"""

from collections.abc import Awaitable, Callable, Sequence

from trainsync.core.logging import get_logger
from trainsync.core.metrics import BOT_UPDATES
from trainsync.entrypoints.bot.commands import (
    COMMANDS,
    Commands,
    UsageError,
    parse_command,
    parse_stats_args,
    period_range,
    week_ranges,
)
from trainsync.integrations.telegram.client import (
    CallbackQuery,
    TelegramApi,
    TelegramError,
    TelegramUnavailableError,
    Update,
)
from trainsync.modules.auth.models import UserRole
from trainsync.modules.chat.assistant import Asker
from trainsync.modules.chat.common import Feature, Incoming, Press, PressResult, Reply
from trainsync.modules.chat.links import ChatLinks, user_context
from trainsync.modules.chat.read_api import ReadApiError
from trainsync.modules.chat.router import ChatOwner
from trainsync.modules.coach.categories import Category
from trainsync.modules.coach.context import using_context
from trainsync.modules.coach.packs import Key, Messages, NeutralKey
from trainsync.modules.coach.voice import CoachVoice

__all__ = [
    "Commands",
    "Dispatcher",
    "TextHandler",
    "UsageError",
    "parse_command",
    "parse_stats_args",
    "period_range",
    "week_ranges",
]

log = get_logger(__name__)

LINK_COMMANDS = frozenset({"link", "unlink"})
# (chat_id, text, who asks) → reply; the assistant plugs in here (P5.7).
TextHandler = Callable[[int, str, Asker], Awaitable[str]]


class Dispatcher:
    """One update in, at most one reply out. Unlinked chats get the link hint only.

    `features` (training, nutrition, check-in) add commands, take plain-text answers to their own
    questions (a pending numbered choice, a check-in step) and handle button presses. Plain text
    nobody claims goes to the assistant.
    """

    def __init__(
        self,
        telegram: TelegramApi,
        commands: Commands,
        links: ChatLinks,
        msg: Messages,
        text_handler: TextHandler | None = None,
        *,
        features: Sequence[Feature] = (),
        voice: CoachVoice | None = None,
        dashboard_url: str = "",
    ) -> None:
        self._telegram = telegram
        self._commands = commands
        self._msg = msg
        self._links = links
        self._text_handler = text_handler
        self._features = tuple(features)
        self._dashboard_url = dashboard_url
        # Savage replies to unknown commands and max-profanity openers (ADR 0032).
        self._voice = voice
        self._known = COMMANDS.union(LINK_COMMANDS, *(f.commands for f in self._features))

    async def handle(self, update: Update) -> None:
        """A linked chat's update runs in its user's voice (tone, language, intensity,
        profanity; ADR 0036) and acts as that user."""
        chat_id = _chat_of(update)
        try:
            owner = await self._links.owner(chat_id) if chat_id is not None else None
        except ReadApiError as exc:
            log.warning("bot_read_api_failed", chat_id=chat_id, error=str(exc))
            if chat_id is not None and update.message is not None:
                await self._send(chat_id, Reply(self._msg(Key.API_DOWN)), "api", "error")
            BOT_UPDATES.labels("none", "error").inc()
            return
        if owner is None:
            await self._handle_unlinked(update)
            return
        with using_context(user_context(owner)):
            await self._handle(update, owner)

    async def _handle_unlinked(self, update: Update) -> None:
        """The link hint, or `/link CODE` (also `/start CODE`: what the dashboard's t.me deep
        link sends); nothing else runs for an unknown chat."""
        message = update.message
        if message is None or not message.text:
            label = "button" if update.callback_query is not None else "none"
            BOT_UPDATES.labels(label, "denied").inc()
            return
        chat_id = message.chat.id
        command, args = parse_command(message.text)
        neutral = self._msg.neutral
        if command == "start" and len(args) == 1:
            command = "link"
        if command != "link":
            await self._send(
                chat_id,
                Reply(neutral(NeutralKey.LINK_HINT, url=self._dashboard_url), plain=True),
                "unlinked",
                "denied",
            )
            log.info("bot_chat_unlinked", chat_id=chat_id)
            BOT_UPDATES.labels(self._label(command), "denied").inc()
            return
        if len(args) != 1:
            text, outcome = neutral(NeutralKey.LINK_USAGE), "usage"
        else:
            try:
                owner = await self._links.link(chat_id, args[0])
            except ReadApiError as exc:
                log.warning("bot_read_api_failed", chat_id=chat_id, error=str(exc))
                owner = None
            if owner is None:
                text, outcome = neutral(NeutralKey.LINK_INVALID), "invalid"
            else:
                with using_context(user_context(owner)):
                    text = neutral(NeutralKey.LINK_DONE, name=owner.display_name)
                outcome = "linked"
        outcome = await self._send(chat_id, Reply(text, plain=True), "link", outcome)
        log.info("bot_update", chat_id=chat_id, command="link", outcome=outcome)
        BOT_UPDATES.labels("link", outcome).inc()

    async def _handle(self, update: Update, owner: ChatOwner) -> None:
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
        incoming = Incoming(chat_id, update.update_id, message.text)
        reply, outcome = await self._reply(incoming, command, args, owner)
        outcome = await self._send(chat_id, reply, label, outcome)
        log.info("bot_update", chat_id=chat_id, command=label, outcome=outcome)
        BOT_UPDATES.labels(label, outcome).inc()

    async def _send(self, chat_id: int, reply: Reply, label: str, outcome: str) -> str:
        if not reply.text:
            return "duplicate"  # a feature recognised a redelivered update: nothing to say
        text = reply.text
        if self._voice is not None and not reply.plain:
            # The settings as stored now: a /lang or /swear switch in this update already counts.
            with using_context(await self._links.prefs(chat_id)):
                text = await self._voice.decorate(text)
        try:
            await self._telegram.send_message(chat_id, text, reply.keyboard)
        except (TelegramError, TelegramUnavailableError) as exc:
            log.warning("bot_reply_failed", chat_id=chat_id, command=label, error=str(exc))
            return "send_failed"
        return outcome

    async def _reply(
        self, incoming: Incoming, command: str | None, args: list[str], owner: ChatOwner
    ) -> tuple[Reply, str]:
        msg = self._msg
        if command == "link":
            return Reply(msg.neutral(NeutralKey.LINK_ALREADY)), "ok"
        if command == "unlink":
            await self._links.unlink(incoming.chat_id)
            return Reply(msg.neutral(NeutralKey.UNLINKED), plain=True), "unlinked"
        try:
            if command is None:
                for feature in self._features:
                    claimed = await feature.text(incoming)
                    if claimed is not None:
                        return claimed, "ok"
                if self._text_handler is None:
                    return Reply(msg(Key.NO_ASSISTANT, help=msg.help())), "ok"
                asker = Asker(owner.user_id, owner.settings.timezone, owner.role is UserRole.OWNER)
                answer = await self._text_handler(incoming.chat_id, incoming.text, asker)
                return Reply(answer, plain=True), "ok"
            for feature in self._features:
                if command in feature.commands:
                    return await feature.command(incoming, command, args), "ok"
            if command not in COMMANDS:
                return Reply(await self._unknown(command)), "unknown"
            return Reply(await self._commands.run(command, args)), "ok"
        except UsageError as exc:
            return Reply(msg(exc.key)), "usage"
        except ReadApiError as exc:
            log.warning("bot_read_api_failed", chat_id=incoming.chat_id, error=str(exc))
            return Reply(msg(Key.API_DOWN)), "error"

    async def _unknown(self, command: str) -> str:
        """In the current tone, pointing to /help: a savage line in savage mode (ADR 0032)."""
        if self._voice is not None and await self._voice.savage():
            line = await self._voice.roast(Category.UNKNOWN_COMMAND)
            return f"{line}\n{self._msg(Key.HELP_POINTER)}"
        return self._msg(Key.UNKNOWN_COMMAND, command=command, help=self._msg.help())

    async def _handle_press(self, update_id: int, query: CallbackQuery) -> None:
        message = query.message
        if message is None:
            BOT_UPDATES.labels("button", "ignored").inc()
            return
        chat_id = message.chat.id
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


def _chat_of(update: Update) -> int | None:
    if update.callback_query is not None:
        message = update.callback_query.message
        return message.chat.id if message is not None else None
    return update.message.chat.id if update.message is not None else None
