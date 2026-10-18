"""A fake Telegram Bot API on respx, plus helpers to build updates and read sent messages."""

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import respx

TELEGRAM = "https://telegram.test"
BOT_TOKEN = "123456:test-bot-token"
BOT_URL = f"{TELEGRAM}/bot{BOT_TOKEN}"


def ok(result: Any = True) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, "result": result})


def error(status: int, description: str, **parameters: Any) -> httpx.Response:
    body: dict[str, Any] = {"ok": False, "error_code": status, "description": description}
    if parameters:
        body["parameters"] = parameters
    return httpx.Response(status, json=body)


def message_update(update_id: int, chat_id: int, text: str) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "date": 1_760_000_000,
            "chat": {"id": chat_id, "type": "private"},
            "text": text,
        },
    }


@dataclass
class SleepRecorder:
    sleeps: list[float] = field(default_factory=list)

    async def __call__(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def sent_messages(route: respx.Route) -> list[dict[str, Any]]:
    """Bodies of the `sendMessage` calls Telegram accepted (status 200) on this route."""
    sent: list[dict[str, Any]] = []
    for call in route.calls:
        if call.response is not None and call.response.status_code == 200:
            sent.append(json.loads(call.request.content))
    return sent
