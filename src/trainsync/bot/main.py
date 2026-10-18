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

import anthropic
from prometheus_client import start_http_server
from redis.asyncio import Redis

from trainsync.bot.assistant import TIMEOUT_S, AnthropicPlanner, Assistant, RedisRateLimiter
from trainsync.bot.checkin import CheckinFlow
from trainsync.bot.coach import CoachFeature
from trainsync.bot.common import Feature, RedisStateStore, StateStore
from trainsync.bot.handlers import Commands, Dispatcher, TextHandler
from trainsync.bot.messages import Messages, messages_for
from trainsync.bot.nutrition import NutritionCommands
from trainsync.bot.polling import Poller
from trainsync.bot.read_api import ReadApi
from trainsync.bot.telegram import TelegramApi
from trainsync.bot.training import TrainingCommands
from trainsync.coach.mode import CoachMode, RedisSoftModeStore, SoftModeStore
from trainsync.coach.voice import CoachVoice, build_voice
from trainsync.core.clock import Clock, Sleep, real_sleep, utc_now
from trainsync.core.logging import configure_logging, get_logger, warn_dev_secrets
from trainsync.core.redis import create_redis
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
    warn_dev_secrets(settings, log)
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
        msg = messages_for(settings)
        redis = create_redis(settings)
        stack.push_async_callback(redis.aclose)
        voice = build_voice(settings, redis, msg)
        soft = RedisSoftModeStore(redis)
        dispatcher = Dispatcher(
            telegram,
            Commands(read_api, clock, msg),
            set(settings.telegram_allowed_chat_ids),
            msg,
            await text_handler(settings, read_api, redis, stack, msg, clock=clock, mode=voice.mode),
            features=features(
                settings,
                read_api,
                RedisStateStore(redis),
                msg,
                clock=clock,
                voice=voice,
                soft=soft,
            ),
        )
        log.info(
            "bot_startup",
            allowed_chats=len(settings.telegram_allowed_chat_ids),
            tone=settings.bot_tone,
            lang=settings.bot_lang,
            intensity=settings.bot_intensity,
            savage=voice.mode.configured,
            local_lines=voice.pack.local_count,
        )
        await Poller(telegram, dispatcher, sleep=sleep).run(stop)
    log.info("bot_shutdown")


def features(
    settings: Settings,
    api: ReadApi,
    store: StateStore,
    msg: Messages,
    *,
    clock: Clock,
    voice: CoachVoice | None = None,
    soft: SoftModeStore | None = None,
) -> list[Feature]:
    """Check-in (P6.9; first, so a check-in answer is never taken for something else), the
    coach (P6.11: pain guard, savage triggers, /yumusak, /sert), training and nutrition commands
    (P6.8). "Today" is the local day in `CHECKIN_TZ`."""
    zone = settings.checkin_zone
    coach: list[Feature] = []
    if voice is not None and soft is not None:
        coach = [CoachFeature(api, voice, soft, clock, zone, msg, settings.workout_reminder_time)]
    return [
        CheckinFlow(api, store, clock, zone, msg, voice),
        *coach,
        TrainingCommands(api, store, clock, zone, msg),
        NutritionCommands(api, store, clock, zone, msg),
    ]


async def text_handler(
    settings: Settings,
    read_api: ReadApi,
    redis: Redis,
    stack: AsyncExitStack,
    msg: Messages,
    *,
    clock: Clock,
    mode: CoachMode | None = None,
) -> TextHandler | None:
    """The natural-language assistant (P5.7), or None without `ANTHROPIC_API_KEY`."""
    if not settings.assistant_enabled:
        log.info("assistant_disabled", reason="ANTHROPIC_API_KEY is empty")
        return None
    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(), timeout=TIMEOUT_S, max_retries=1
    )
    stack.push_async_callback(client.close)
    assistant = Assistant(
        AnthropicPlanner(client, settings.assistant_model),
        read_api,
        RedisRateLimiter(redis, settings.assistant_rate_limit_per_hour, clock),
        clock,
        msg,
        mode=mode,
    )
    log.info("assistant_enabled", model=settings.assistant_model)
    return assistant.answer


def main() -> None:
    settings = get_settings()

    async def _main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await run(settings, stop)

    asyncio.run(_main())
