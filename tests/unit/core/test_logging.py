import json

import pytest
import structlog

from trainsync.core.logging import REDACTED, configure_logging, get_logger, redact_secrets
from trainsync.core.settings import Settings


def test_redacts_sensitive_keys_recursively() -> None:
    event = {
        "event": "x",
        "access_token": "a",
        "Authorization": "Bearer b",
        "client_secret": "c",
        "nested": {"refresh_token": "d", "ok": 1, "items": [{"password": "e"}]},
        "API_KEY": "f",
        "athlete_id": 42,
    }
    out = redact_secrets(None, "info", event)
    assert out == {
        "event": "x",
        "access_token": REDACTED,
        "Authorization": REDACTED,
        "client_secret": REDACTED,
        "nested": {"refresh_token": REDACTED, "ok": 1, "items": [{"password": REDACTED}]},
        "API_KEY": REDACTED,
        "athlete_id": 42,
    }


def test_json_log_output_never_contains_secrets(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(settings)
    with structlog.contextvars.bound_contextvars(request_id="r1"):
        get_logger("t").info("token_refreshed", access_token="s3cr3t", athlete_id=1)
    line = capsys.readouterr().out.strip()
    payload = json.loads(line)
    assert "s3cr3t" not in line
    assert payload["access_token"] == REDACTED
    assert payload["request_id"] == "r1"
    assert payload["level"] == "info"
    assert payload["timestamp"].endswith("Z")
