"""`/v1/chats/{id}/settings` backed by a dict: the database, as far as the bot can tell
(P6.12, P6.13)."""

import json
import re

import httpx
import respx

from trainsync.core.settings import BotLang, BotProfanity

FIELDS = ("lang", "profanity")


class ChatSettingsApi:
    def __init__(self) -> None:
        self.rows: dict[int, dict[str, str | None]] = {}
        self.reads = 0
        self.down = False

    def lang(self, chat_id: int) -> BotLang | None:
        value = self.rows.get(chat_id, {}).get("lang")
        return "tr" if value == "tr" else "en" if value == "en" else None

    def profanity(self, chat_id: int) -> BotProfanity | None:
        value = self.rows.get(chat_id, {}).get("profanity")
        return "max" if value == "max" else "roast" if value == "roast" else None

    def _out(self, chat_id: int) -> dict[str, object]:
        row = self.rows.get(chat_id, {})
        return {"chat_id": chat_id, **{name: row.get(name) for name in FIELDS}}

    def get(self, request: httpx.Request, chat_id: str) -> httpx.Response:
        self.reads += 1
        if self.down:
            return httpx.Response(503, json={"detail": "down"})
        return httpx.Response(200, json=self._out(int(chat_id)))

    def put(self, request: httpx.Request, chat_id: str) -> httpx.Response:
        body = json.loads(request.content)
        row = self.rows.setdefault(int(chat_id), {})
        row.update({name: body[name] for name in FIELDS if body.get(name) is not None})
        return httpx.Response(200, json=self._out(int(chat_id)))

    def install(self, router: respx.MockRouter, api: str) -> None:
        url = rf"{re.escape(api)}/v1/chats/(?P<chat_id>\d+)/settings"
        router.get(url__regex=url).mock(side_effect=self.get)
        router.put(url__regex=url).mock(side_effect=self.put)
