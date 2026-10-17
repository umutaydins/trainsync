"""Signed, expiring OAuth `state` values: `<nonce>.<issued_at>.<hmac>` (URL-safe base64)."""

import base64
import binascii
import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pydantic import SecretStr

DEFAULT_MAX_AGE = timedelta(minutes=10)
CLOCK_SKEW = timedelta(seconds=30)
_NONCE_BYTES = 16

SigningKey = SecretStr | bytes


class InvalidStateError(Exception):
    """The OAuth state is malformed, forged or expired."""


def sign_state(
    now: datetime,
    key: SigningKey,
    *,
    token_bytes: Callable[[int], bytes] = secrets.token_bytes,
) -> str:
    nonce = _b64encode(token_bytes(_NONCE_BYTES))
    issued_at = _b64encode(str(int(now.timestamp())).encode())
    payload = f"{nonce}.{issued_at}"
    return f"{payload}.{_signature(payload, key)}"


def verify_state(
    value: str,
    now: datetime,
    key: SigningKey,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> None:
    parts = value.split(".")
    if len(parts) != 3 or not all(parts):
        raise InvalidStateError("malformed state")
    nonce, issued_at_b64, signature = parts
    expected = _signature(f"{nonce}.{issued_at_b64}", key)
    if not hmac.compare_digest(signature.encode(), expected.encode()):
        raise InvalidStateError("state signature mismatch")
    try:
        issued_at = datetime.fromtimestamp(int(_b64decode(issued_at_b64)), tz=UTC)
    except (ValueError, binascii.Error, OverflowError, OSError):
        raise InvalidStateError("malformed state timestamp") from None
    if issued_at - now > CLOCK_SKEW:
        raise InvalidStateError("state issued in the future")
    if now - issued_at > max_age:
        raise InvalidStateError("state expired")


def _signature(payload: str, key: SigningKey) -> str:
    raw_key = key.get_secret_value().encode() if isinstance(key, SecretStr) else key
    return _b64encode(hmac.new(raw_key, payload.encode(), hashlib.sha256).digest())


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
