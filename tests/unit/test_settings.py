import pytest
from pydantic import ValidationError

from tests.conftest import TEST_ENV
from trainsync.core.settings import Settings, get_settings


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def test_loads_from_env(env: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    assert settings.env == "test"
    assert settings.strava_client_id == "1234"
    assert settings.strava_webhook_subscription_id == 999
    assert settings.strava_api_base_url == "https://www.strava.com/api/v3"


def test_missing_required_variable_is_a_clear_error(env: pytest.MonkeyPatch) -> None:
    env.delenv("TOKEN_ENCRYPTION_KEY")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]
    errors = exc_info.value.errors()
    assert [(e["loc"], e["type"]) for e in errors] == [(("token_encryption_key",), "missing")]


def test_api_keys_parse_from_comma_separated_string(env: pytest.MonkeyPatch) -> None:
    env.setenv("API_KEYS", "a, b")
    keys = get_settings().api_keys
    assert [k.get_secret_value() for k in keys] == ["a", "b"]


def test_empty_api_keys_rejected(env: pytest.MonkeyPatch) -> None:
    env.setenv("API_KEYS", " , ")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_empty_subscription_id_is_none(env: pytest.MonkeyPatch) -> None:
    env.setenv("STRAVA_WEBHOOK_SUBSCRIPTION_ID", "")
    assert get_settings().strava_webhook_subscription_id is None


def test_repr_never_contains_secrets(env: pytest.MonkeyPatch) -> None:
    rendered = repr(get_settings()) + str(get_settings())
    for key in (
        "STRAVA_CLIENT_SECRET",
        "STRAVA_WEBHOOK_VERIFY_TOKEN",
        "TOKEN_ENCRYPTION_KEY",
        "STATE_SIGNING_KEY",
        "API_KEYS",
    ):
        assert TEST_ENV[key] not in rendered
