"""`Notifier` over the Telegram Bot API (the same client the bot uses)."""

from trainsync.integrations.notifier import DeliveryUnknownError, NotifyFailedError
from trainsync.integrations.telegram.client import (
    TelegramApi,
    TelegramDeliveryUnknownError,
    TelegramError,
    TelegramRetryAfterError,
    TelegramUnavailableError,
)


class TelegramNotifier:
    channel = "telegram"

    def __init__(self, api: TelegramApi) -> None:
        self._api = api

    async def send(self, chat_ref: str, text: str) -> None:
        try:
            await self._api.send_message(int(chat_ref), text)
        except TelegramRetryAfterError as exc:
            raise NotifyFailedError(str(exc), retry_after=exc.retry_after) from None
        except TelegramDeliveryUnknownError as exc:
            raise DeliveryUnknownError(str(exc)) from None
        except (TelegramUnavailableError, TelegramError) as exc:
            raise NotifyFailedError(str(exc)) from None
