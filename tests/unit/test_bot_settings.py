"""Bot/notification settings are optional: the API and the worker start without them."""

from pydantic import SecretStr

from tests.conftest import make_settings


def test_bot_settings_default_to_disabled() -> None:
    settings = make_settings()
    assert not settings.bot_enabled
    assert settings.telegram_allowed_chat_ids == []
    assert settings.notify_chat_id() is None
    assert settings.dashboard_public_url == ""


def test_chat_ids_parse_and_notify_chat_falls_back_to_first_allowed() -> None:
    settings = make_settings(telegram_allowed_chat_ids=" 42, -1001 ,", telegram_notify_chat_id="")
    assert settings.telegram_allowed_chat_ids == [42, -1001]
    assert settings.notify_chat_id() == 42
    assert make_settings(telegram_notify_chat_id="7").notify_chat_id() == 7


def test_bot_api_key_falls_back_to_first_api_key() -> None:
    assert make_settings().bot_read_api_key().get_secret_value() == "test-api-key"
    explicit = make_settings(bot_api_key=SecretStr("bot-only"))
    assert explicit.bot_read_api_key().get_secret_value() == "bot-only"


def test_token_is_not_in_repr() -> None:
    settings = make_settings(telegram_bot_token="123:secret-token")
    assert settings.bot_enabled
    assert "secret-token" not in repr(settings)
