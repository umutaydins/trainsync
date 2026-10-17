from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet

from trainsync.core.settings import Settings, get_settings

TEST_FERNET_KEY = Fernet.generate_key().decode()

TEST_ENV = {
    "ENV": "test",
    "STRAVA_CLIENT_ID": "1234",
    "STRAVA_CLIENT_SECRET": "client-secret-value",
    "STRAVA_WEBHOOK_VERIFY_TOKEN": "verify-token-value",
    "STRAVA_WEBHOOK_SUBSCRIPTION_ID": "999",
    "TOKEN_ENCRYPTION_KEY": TEST_FERNET_KEY,
    "STATE_SIGNING_KEY": "state-signing-key-value",
    "API_KEYS": "test-api-key",
}


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {k.lower(): v for k, v in TEST_ENV.items()}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
