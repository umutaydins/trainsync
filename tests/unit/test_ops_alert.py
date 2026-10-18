"""Operational alerts to Telegram (P7.4 backups, reused by P7.8). Nothing is ever sent here."""

import json

import pytest

from trainsync.ops.alert import chat_id, main, send

TOKEN = "123:test-token"


class Recorder:
    def __init__(self, status: int = 200, error: OSError | None = None) -> None:
        self.status, self.error = status, error
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, url: str, body: bytes) -> int:
        self.calls.append((url, json.loads(body)))
        if self.error:
            raise self.error
        return self.status


def test_not_configured_is_a_quiet_no_op(capsys: pytest.CaptureFixture[str]) -> None:
    post = Recorder()
    assert send("hi", {}, post) is None
    assert send("hi", {"TELEGRAM_BOT_TOKEN": TOKEN}, post) is None
    assert main(["hi"], {}, post) == 0
    assert post.calls == []
    assert "not configured" in capsys.readouterr().out


def test_chat_falls_back_to_the_first_allowed_chat() -> None:
    assert chat_id({"TELEGRAM_NOTIFY_CHAT_ID": " 42 "}) == "42"
    assert chat_id({"TELEGRAM_ALLOWED_CHAT_IDS": " , 7, 8"}) == "7"
    assert chat_id({"TELEGRAM_ALLOWED_CHAT_IDS": ""}) is None


def test_sends_to_the_configured_chat(capsys: pytest.CaptureFixture[str]) -> None:
    post = Recorder()
    env = {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_NOTIFY_CHAT_ID": "42"}
    assert main(["backup", "failed"], env, post) == 0
    url, body = post.calls[0]
    assert url == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert body == {"chat_id": "42", "text": "backup failed", "disable_web_page_preview": True}
    assert TOKEN not in capsys.readouterr().out


@pytest.mark.parametrize("post", [Recorder(status=500), Recorder(error=TimeoutError("slow"))])
def test_failed_send_exits_1_without_leaking_the_token(
    post: Recorder, capsys: pytest.CaptureFixture[str]
) -> None:
    env = {
        "TELEGRAM_BOT_TOKEN": TOKEN,
        "TELEGRAM_ALLOWED_CHAT_IDS": "7",
        "TELEGRAM_API_BASE_URL": "http://telegram.test",
    }
    assert main(["x"], env, post) == 1
    assert post.calls[0][0].startswith("http://telegram.test/bot")
    captured = capsys.readouterr()
    assert TOKEN not in captured.out + captured.err


def test_usage() -> None:
    assert main([], {}) == 2
