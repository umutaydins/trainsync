from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr

from trainsync.core.state import (
    InvalidStateError,
    _b64encode,
    _signature,
    sign_state,
    verify_state,
)

KEY = SecretStr("state-signing-key-value")
OTHER_KEY = SecretStr("other-key")
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def _fixed_nonce(n: int) -> bytes:
    return b"\x01" * n


def _replace_first_char(part: str) -> str:
    return ("A" if part[0] != "A" else "B") + part[1:]


def test_valid_state_verifies() -> None:
    state = sign_state(NOW, KEY)
    verify_state(state, NOW + timedelta(minutes=9), KEY)
    verify_state(state, NOW, KEY.get_secret_value().encode())


def test_format_and_determinism_with_injected_nonce() -> None:
    state = sign_state(NOW, KEY, token_bytes=_fixed_nonce)
    assert state == sign_state(NOW, KEY, token_bytes=_fixed_nonce)
    nonce, issued_at, signature = state.split(".")
    assert nonce == _b64encode(b"\x01" * 16)
    for char in "=+/":
        assert char not in state
    assert issued_at
    assert signature
    assert state != sign_state(NOW, KEY)


def _case(kind: str) -> tuple[str, datetime, SecretStr]:
    nonce, issued_at, signature = sign_state(NOW, KEY).split(".")
    later = _b64encode(str(int((NOW + timedelta(hours=1)).timestamp())).encode())
    cases: dict[str, tuple[str, datetime, SecretStr]] = {
        "nonce": (f"{_replace_first_char(nonce)}.{issued_at}.{signature}", NOW, KEY),
        "timestamp": (f"{nonce}.{later}.{signature}", NOW, KEY),
        "signature": (f"{nonce}.{issued_at}.{_replace_first_char(signature)}", NOW, KEY),
        "wrong_key": (f"{nonce}.{issued_at}.{signature}", NOW, OTHER_KEY),
        "expired": (f"{nonce}.{issued_at}.{signature}", NOW + timedelta(minutes=11), KEY),
        "future": (f"{nonce}.{issued_at}.{signature}", NOW - timedelta(minutes=5), KEY),
        "missing_part": (f"{nonce}.{issued_at}", NOW, KEY),
        "extra_part": (f"{nonce}.{issued_at}.{signature}.x", NOW, KEY),
        "empty": ("", NOW, KEY),
        "empty_part": (f"{nonce}..{signature}", NOW, KEY),
    }
    return cases[kind]


@pytest.mark.parametrize(
    "kind",
    [
        "nonce",
        "timestamp",
        "signature",
        "wrong_key",
        "expired",
        "future",
        "missing_part",
        "extra_part",
        "empty",
        "empty_part",
    ],
)
def test_invalid_states_raise(kind: str) -> None:
    value, now, key = _case(kind)
    with pytest.raises(InvalidStateError) as exc_info:
        verify_state(value, now, key)
    message = str(exc_info.value)
    assert KEY.get_secret_value() not in message
    assert OTHER_KEY.get_secret_value() not in message
    if value:
        assert value not in message


def test_signed_non_numeric_timestamp_is_malformed() -> None:
    payload = f"{_b64encode(b'n')}.{_b64encode(b'not-a-number')}"
    with pytest.raises(InvalidStateError, match="timestamp"):
        verify_state(f"{payload}.{_signature(payload, KEY)}", NOW, KEY)


def test_custom_max_age() -> None:
    state = sign_state(NOW, KEY)
    with pytest.raises(InvalidStateError, match="expired"):
        verify_state(state, NOW + timedelta(minutes=2), KEY, max_age=timedelta(minutes=1))


def test_state_without_data_returns_empty_string() -> None:
    assert verify_state(sign_state(NOW, KEY), NOW, KEY) == ""


def test_state_carries_signed_data() -> None:
    state = sign_state(NOW, KEY, data="http://localhost:3000/sync")
    assert len(state.split(".")) == 4
    assert verify_state(state, NOW, KEY) == "http://localhost:3000/sync"


def test_state_data_cannot_be_swapped() -> None:
    nonce, issued_at, _data, signature = sign_state(NOW, KEY, data="http://ok/sync").split(".")
    forged = f"{nonce}.{issued_at}.{_b64encode(b'https://evil.example')}.{signature}"
    with pytest.raises(InvalidStateError, match="signature"):
        verify_state(forged, NOW, KEY)
    # Dropping the data part does not verify either: the signature covers it.
    with pytest.raises(InvalidStateError, match="signature"):
        verify_state(f"{nonce}.{issued_at}.{signature}", NOW, KEY)


def test_signed_undecodable_data_is_malformed() -> None:
    issued_at = _b64encode(str(int(NOW.timestamp())).encode())
    payload = f"{_b64encode(b'n')}.{issued_at}.{_b64encode(bytes([0xFF, 0xFE]))}"
    with pytest.raises(InvalidStateError, match="data"):
        verify_state(f"{payload}.{_signature(payload, KEY)}", NOW, KEY)
