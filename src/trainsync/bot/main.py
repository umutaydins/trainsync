"""Bot entry point: `python -m trainsync.bot`.

Without `TELEGRAM_BOT_TOKEN` the bot does not poll: it only serves its metrics and waits for a
shutdown signal, so the compose service stays up (and healthy) in a stack without a token.
SIGTERM / SIGINT stop it gracefully: the pending long poll is cancelled, a reply being sent is
finished, the HTTP client is closed.
"""

import asyncio
import logging
import signal
from contextlib import AsyncExitStack

from prometheus_client import start_http_server

from trainsync.bot.handlers import Commands, Dispatcher, TextHandler
from trainsync.bot.polling import Poller
from trainsync.bot.read_api import ReadApi
from trainsync.bot.telegram import TelegramApi
from trainsync.core.clock import Clock, Sleep, real_sleep, utc_now
from trainsync.core.logging import configure_logging, get_logger
from trainsync.core.settings import Settings, get_settings
from trainsync.strava.http import build_http_client

log = get_logger(__name__)


async def run(
    settings: Settings,
    stop: asyncio.Event,
    *,
    clock: Clock = utc_now,
    sleep: Sleep = real_sleep,
) -> None:
    configure_logging(settings)
    # httpx logs request URLs at INFO, and Telegram URLs contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    async with AsyncExitStack() as stack:
        if settings.bot_metrics_port:
            server, _ = start_http_server(settings.bot_metrics_port)
            stack.callback(server.server_close)
            stack.callback(server.shutdown)
        if not settings.bot_enabled:
            log.info("bot_disabled", reason="TELEGRAM_BOT_TOKEN is empty")
            await stop.wait()
            return
        http = build_http_client(settings)
        stack.push_async_callback(http.aclose)
        telegram = TelegramApi(
            http, settings.telegram_bot_token, base_url=settings.telegram_api_base_url, sleep=sleep
        )
        read_api = ReadApi(http, settings.bot_api_base_url, settings.bot_read_api_key())
        dispatcher = Dispatcher(
            telegram,
            Commands(read_api, clock),
            set(settings.telegram_allowed_chat_ids),
            await text_handler(settings, read_api, stack, clock=clock),
        )
        log.info("bot_startup", allowed_chats=len(settings.telegram_allowed_chat_ids))
        await Poller(telegram, dispatcher, sleep=sleep).run(stop)
    log.info("bot_shutdown")


async def text_handler(
    settings: Settings, read_api: ReadApi, stack: AsyncExitStack, *, clock: Clock
) -> TextHandler | None:
    """The natural-language assistant (P5.7), or None when it is not configured."""
    del settings, read_api, stack, clock
    return None


def main() -> None:
    settings = get_settings()

    async def _main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await run(settings, stop)

    asyncio.run(_main())
