"""docker-compose.yml dev-only secrets: overridable from .env, labelled, and a startup warning when
a production run (ENV=prod) still uses one of the defaults."""

import json
import re
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from tests.conftest import make_settings
from trainsync.core.logging import configure_logging, get_logger, warn_dev_secrets
from trainsync.core.settings import DEV_ONLY_SECRETS, Settings, is_dev_default

COMPOSE = (Path(__file__).parents[3] / "docker-compose.yml").read_text(encoding="utf-8")
# The dev values come from the compose file only; the code finds them by their label.
DEFAULTS = dict(re.findall(r"\$\{([A-Z0-9_]+):-([^}]*)\}", COMPOSE))
WEB_SECRETS = ("TRAINSYNC_API_KEY", "DASHBOARD_PASSWORD", "DASHBOARD_SESSION_SECRET")


def compose_defaults(env: str = "prod") -> Settings:
    return make_settings(env=env, **{name.lower(): DEFAULTS[name] for name in DEV_ONLY_SECRETS})


def test_every_secret_in_compose_is_overridable_and_labelled_dev_only() -> None:
    for name in (*DEV_ONLY_SECRETS, *WEB_SECRETS):
        assert name in DEFAULTS, f"{name} is not ${{{name}:-default}} in docker-compose.yml"
        assert is_dev_default(DEFAULTS[name]), name
        assert not re.search(rf"^\s*{name}: (?!\$\{{)", COMPOSE, re.MULTILINE), name
    assert "DEV-ONLY" in COMPOSE.splitlines()[0]


def test_the_dev_fernet_key_is_valid_and_says_what_it_is() -> None:
    key = DEFAULTS["TOKEN_ENCRYPTION_KEY"]
    Fernet(key)  # the stack must start with it
    assert is_dev_default(key)
    assert not is_dev_default(Fernet.generate_key().decode())


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("dev-only-anything", True),
        ("dev-key-1", True),
        ("a-real-long-random-secret", False),
        ("not base64 !!", False),
        ("", False),
    ],
)
def test_is_dev_default(value: str, expected: bool) -> None:
    assert is_dev_default(value) is expected


def test_dev_defaults_are_detected_by_name() -> None:
    assert compose_defaults().dev_secrets_in_use() == list(DEV_ONLY_SECRETS)
    assert make_settings().dev_secrets_in_use() == []
    # A dev key anywhere in a list counts: it still opens the API or decrypts tokens.
    own_key = make_settings().token_encryption_key.get_secret_value()
    mixed = make_settings(
        api_keys="real-key,dev-key-1",
        token_encryption_key=f"{own_key},{DEFAULTS['TOKEN_ENCRYPTION_KEY']}",
    )
    assert mixed.dev_secrets_in_use() == ["TOKEN_ENCRYPTION_KEY", "API_KEYS"]


def test_prod_with_dev_defaults_warns_with_names_never_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = compose_defaults()
    configure_logging(settings)
    assert warn_dev_secrets(settings, get_logger("t")) == list(DEV_ONLY_SECRETS)
    line = capsys.readouterr().out.strip()
    payload = json.loads(line)
    assert payload["event"] == "dev_default_secrets_in_prod"
    assert payload["level"] == "warning"
    assert payload["variables"] == list(DEV_ONLY_SECRETS)
    for name in DEV_ONLY_SECRETS:
        assert DEFAULTS[name] not in line


@pytest.mark.parametrize("env", ["dev", "test"])
def test_no_warning_outside_prod(env: str, capsys: pytest.CaptureFixture[str]) -> None:
    settings = compose_defaults(env)
    configure_logging(settings)
    assert warn_dev_secrets(settings, get_logger("t")) == []
    assert capsys.readouterr().out == ""


def test_no_warning_in_prod_with_own_secrets(capsys: pytest.CaptureFixture[str]) -> None:
    settings = make_settings(env="prod")
    configure_logging(settings)
    assert warn_dev_secrets(settings, get_logger("t")) == []
    assert capsys.readouterr().out == ""
