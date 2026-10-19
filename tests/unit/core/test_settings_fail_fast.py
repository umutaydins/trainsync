"""P7.1: a missing or invalid secret stops the process with a message naming the variable."""

import pytest

from tests.conftest import TEST_ENV
from trainsync.core.settings import get_settings


def test_missing_secret_exits_naming_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir("/")  # no .env to read
    for name, value in TEST_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEY")
    monkeypatch.setenv("API_KEYS", "")
    get_settings.cache_clear()
    with pytest.raises(SystemExit) as exc:
        get_settings()
    message = str(exc.value)
    assert message.startswith("trainsync: missing or invalid settings: ")
    assert "TOKEN_ENCRYPTION_KEY (missing)" in message
    assert "API_KEYS (invalid)" in message
    assert ".env.prod.example" in message


def test_values_never_appear_in_the_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir("/")
    for name, value in TEST_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("STRAVA_WEBHOOK_SUBSCRIPTION_ID", "not-a-number-secret-ish")
    get_settings.cache_clear()
    with pytest.raises(SystemExit) as exc:
        get_settings()
    assert "STRAVA_WEBHOOK_SUBSCRIPTION_ID (invalid)" in str(exc.value)
    assert "not-a-number-secret-ish" not in str(exc.value)
