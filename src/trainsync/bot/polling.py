"""Long polling loop (`getUpdates`): no public URL needed.

Updates are handled one at a time, in order. `offset` moves past an update before it is handled,
so an update that makes the handler fail is never replayed in a loop. On shutdown the pending
long poll (or backoff wait) is cancelled; an update that is being handled is finished first.
"""

import asyncio
import contextlib
from collections.abc import Awaitable

from trainsync.bot.handlers import Dispatcher
from trainsync.bot.telegram import (
    POLL_TIMEOUT_S,
    TelegramApi,
    TelegramError,
    TelegramRetryAfterError,
    TelegramUnavailableError,
    Update,
    backoff_delay,
)
from trainsync.core.clock import Sleep, real_sleep
from trainsync.core.logging import get_logger

log = get_logger(__name__)


class Poller:
    def __init__(
        self,
        telegram: TelegramApi,
        dispatcher: Dispatcher,
        *,
        sleep: Sleep = real_sleep,
        poll_timeout: int = POLL_TIMEOUT_S,
    ) -> None:
        self._telegram = telegram
        self._dispatcher = dispatcher
        self._sleep = sleep
        self._poll_timeout = poll_timeout
        self.offset: int | None = None
        self._failures = 0

    async def run(self, stop: asyncio.Event) -> None:
        log.info("bot_polling_started")
        while not stop.is_set():
            fetched = await _until_stopped(self.fetch(), stop)
            if fetched is None:
                break
            updates, delay = fetched
            await self.handle(updates)  # not interrupted by `stop`
            if delay:
                await _until_stopped(self._sleep(delay), stop)
        log.info("bot_polling_stopped")

    async def poll_once(self) -> float:
        """One fetch + handle round; returns the wait before the next round."""
        updates, delay = await self.fetch()
        await self.handle(updates)
        return delay

    async def fetch(self) -> tuple[list[Update], float]:
        """The next batch of updates, or none and how long to wait (429 / outage backoff)."""
        try:
            updates = await self._telegram.get_updates(self.offset, poll_timeout=self._poll_timeout)
        except TelegramRetryAfterError as exc:
            log.info("bot_poll_retry_after", retry_after=exc.retry_after)
            return [], exc.retry_after
        except (TelegramUnavailableError, TelegramError) as exc:
            self._failures += 1
            delay = backoff_delay(self._failures)
            log.warning("bot_poll_failed", error=str(exc), retry_in_s=delay)
            return [], delay
        self._failures = 0
        return updates, 0.0

    async def handle(self, updates: list[Update]) -> None:
        for update in updates:
            self.offset = update.update_id + 1
            await self._dispatcher.handle(update)


async def _until_stopped[T](work: Awaitable[T], stop: asyncio.Event) -> T | None:
    """Await `work` unless `stop` is set first; then cancel it and return None."""
    task = asyncio.ensure_future(work)
    stopper = asyncio.ensure_future(stop.wait())
    try:
        done, _ = await asyncio.wait({task, stopper}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        stopper.cancel()
    if task in done:
        return task.result()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    return None
