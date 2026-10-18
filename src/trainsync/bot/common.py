"""Small pieces shared by the bot's command groups: replies, the conversation state store,
deterministic client ids and number formatting."""

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from redis.asyncio import Redis

from trainsync.bot.parsing import ParsedSet
from trainsync.bot.telegram import Keyboard

# uuid5 namespace for every client id the bot derives (ADR 0017): the same Telegram update or
# check-in step always maps to the same id, so a redelivered update stores nothing twice.
CLIENT_ID_NAMESPACE = uuid.UUID("6c1d1f0e-3b5a-4f0e-9a51-7b1f2f3c8e10")


def client_id(name: str) -> uuid.UUID:
    """`tg:{chat}:{update}:{n}` (commands) or `checkin:{date}:{exercise}:{set}` (check-in)."""
    return uuid.uuid5(CLIENT_ID_NAMESPACE, name)


@dataclass(frozen=True, slots=True)
class Reply:
    text: str
    keyboard: Keyboard | None = None


@dataclass(frozen=True, slots=True)
class Incoming:
    """A text message from an allowlisted chat."""

    chat_id: int
    update_id: int
    text: str


@dataclass(frozen=True, slots=True)
class Press:
    """A button press (callback query) from an allowlisted chat."""

    chat_id: int
    update_id: int
    data: str
    message_id: int | None


@dataclass(frozen=True, slots=True)
class PressResult:
    """`toast` answers the callback query; `reply` (if any) is sent as a new message;
    `accepted` takes the buttons off the pressed message."""

    toast: str = ""
    reply: Reply | None = None
    accepted: bool = False


class StateStore(Protocol):
    """Short-lived conversation state (pending choices, the check-in flow). Redis in the bot;
    an in-memory dict in unit tests."""

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl_s: int) -> None: ...

    async def delete(self, key: str) -> None: ...


class RedisStateStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> str | None:
        value = await self._redis.get(key)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        await self._redis.set(key, value, ex=ttl_s)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)


# ---------------------------------------------------------------- pending numbered choices

PENDING_TTL_S = 15 * 60


@dataclass(frozen=True, slots=True)
class Pending:
    """A numbered list the owner was asked to pick from (`/log` exercise, `/eat` food)."""

    kind: str  # "log" | "eat"
    update_id: int  # the command's update: client ids derive from it
    options: list[tuple[int, str]]  # (id, label)
    payload: dict[str, str]


def pending_key(chat_id: int) -> str:
    return f"bot:pending:{chat_id}"


async def load_pending(store: StateStore, chat_id: int) -> Pending | None:
    raw = await store.get(pending_key(chat_id))
    if raw is None:
        return None
    data = json.loads(raw)
    return Pending(
        kind=str(data["kind"]),
        update_id=int(data["update_id"]),
        options=[(int(i), str(label)) for i, label in data["options"]],
        payload={str(k): str(v) for k, v in data["payload"].items()},
    )


async def save_pending(store: StateStore, chat_id: int, pending: Pending) -> None:
    data = {
        "kind": pending.kind,
        "update_id": pending.update_id,
        "options": pending.options,
        "payload": pending.payload,
    }
    await store.set(pending_key(chat_id), json.dumps(data), PENDING_TTL_S)


def numbered(labels: Sequence[str]) -> str:
    return "\n".join(f"{n}. {label}" for n, label in enumerate(labels, start=1))


# ---------------------------------------------------------------- numbers


def number(value: Decimal | float, places: int = 2) -> str:
    """`80`, `82.5`, `1.25`: no trailing zeros."""
    text = f"{Decimal(str(value)):.{places}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def kg(value: Decimal | float) -> str:
    return f"{number(value)} kg"


def thousands(value: Decimal | float) -> str:
    """`8,240 kg`: volumes, with a thousands separator."""
    return f"{round(float(value)):,} kg"


def sets_text(sets: Sequence[ParsedSet]) -> str:
    """`80 kg x 5, 5, 4`, `bw x 12, 12, 12`; mixed loads as `80 kg x 5, 85 kg x 3`."""
    if not sets:
        return ""
    loads = {s.weight_kg for s in sets}
    if len(loads) == 1:
        load = "bw" if sets[0].weight_kg == 0 else kg(sets[0].weight_kg)
        return f"{load} x {', '.join(str(s.reps) for s in sets)}"
    return ", ".join(f"{'bw' if s.weight_kg == 0 else kg(s.weight_kg)} x {s.reps}" for s in sets)


class Feature(Protocol):
    """A group of bot commands (training, nutrition, check-in). The dispatcher offers every
    plain-text message and button press to each feature in turn; `None` means "not mine"."""

    @property
    def commands(self) -> frozenset[str]: ...

    async def command(self, incoming: Incoming, command: str, args: list[str]) -> Reply: ...

    async def text(self, incoming: Incoming) -> Reply | None: ...

    async def press(self, press: Press) -> PressResult | None: ...
