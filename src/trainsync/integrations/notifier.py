"""The `Notifier` protocol and the errors every implementation maps its failures to."""

from typing import Protocol


class NotifyFailedError(Exception):
    """The message was not delivered; trying again later is safe. `retry_after` (seconds) is set
    when the channel said how long to wait."""

    def __init__(self, reason: str, *, retry_after: float | None = None) -> None:
        super().__init__(reason)
        self.retry_after = retry_after


class DeliveryUnknownError(Exception):
    """The request went out but no answer came back: it may have been delivered. Not retried,
    because a retry could send the message twice."""


class Notifier(Protocol):
    """Sends one plain-text message to `chat_ref` (a Telegram chat id, later a phone number)."""

    @property
    def channel(self) -> str: ...

    async def send(self, chat_ref: str, text: str) -> None: ...


class NullNotifier:
    """The default when no channel is configured: sends nothing."""

    channel = "null"

    async def send(self, chat_ref: str, text: str) -> None:
        return None
