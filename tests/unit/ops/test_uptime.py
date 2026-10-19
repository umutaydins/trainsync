"""External uptime alert machine (P7.8): down once, silent while down, recovered once, flapping
never alerts. Nothing is ever sent or fetched: the probe and the Telegram post are stubs."""

import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from trainsync.ops.uptime import (
    Message,
    Status,
    TargetState,
    load_state,
    main,
    probe,
    save_state,
    step,
    targets,
)

T0 = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
TOKEN = "123:test-token"
ENV = {
    "UPTIME_URL": "https://mac.tail.ts.net/",
    "TELEGRAM_BOT_TOKEN": TOKEN,
    "TELEGRAM_NOTIFY_CHAT_ID": "42",
    "TELEGRAM_API_BASE_URL": "http://telegram.test",
}
REAL = "https://mac.tail.ts.net/health/ready"


def run_machine(results: list[bool]) -> list[Message]:
    state, messages = TargetState(), []
    for i, ok in enumerate(results):
        state, message = step(state, ok, T0 + timedelta(minutes=15 * i))
        messages.append(message)
    return messages


def test_down_after_two_failures_then_silent_then_recovered_once() -> None:
    messages = run_machine([True, False, False, False, False, True, True])
    assert messages == [
        Message.NONE,
        Message.NONE,  # failing(1)
        Message.DOWN,  # failing(2) -> down
        Message.NONE,  # still down
        Message.NONE,
        Message.RECOVERED,
        Message.NONE,
    ]


def test_flapping_never_alerts() -> None:
    assert set(run_machine([False, True] * 6)) == {Message.NONE}


def test_states_and_outage_start() -> None:
    state, _ = step(TargetState(), False, T0)
    assert (state.status, state.failures, state.since) == (Status.FAILING, 1, T0)
    state, _ = step(state, False, T0 + timedelta(minutes=15))
    assert (state.status, state.failures, state.since) == (Status.DOWN, 2, T0)
    state, message = step(state, True, T0 + timedelta(minutes=30))
    assert state == TargetState()
    assert message is Message.RECOVERED


def test_threshold_one_alerts_on_the_first_failure() -> None:
    assert step(TargetState(), False, T0, threshold=1)[1] is Message.DOWN


def test_state_round_trips_and_garbage_is_a_fresh_up(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    states = {"real": TargetState(Status.DOWN, 3, T0), "demo": TargetState()}
    save_state(path, states)
    assert load_state(path) == states
    assert load_state(tmp_path / "missing.json") == {}
    path.write_text("[1]")
    assert load_state(path) == {}
    path.write_text(json.dumps({"real": {"status": "sideways"}, "demo": 7}))
    assert load_state(path) == {"real": TargetState(), "demo": TargetState()}


def test_targets_from_env() -> None:
    assert targets({}) == {}
    assert targets({"UPTIME_URL": " ", "UPTIME_DEMO_URL": "https://d.ts.net:8443"}) == {
        "demo": "https://d.ts.net:8443/health/ready"
    }


class Telegram:
    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.texts: list[str] = []
        self.urls: list[str] = []

    def __call__(self, url: str, body: bytes) -> int:
        self.urls.append(url)
        self.texts.append(json.loads(body)["text"])
        return self.status


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        current = self.now
        self.now += timedelta(minutes=15)
        return current


def runs(results: list[str | None]) -> Iterator[str | None]:
    yield from results


def test_main_end_to_end_with_a_state_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state = tmp_path / "uptime.json"
    telegram, clock = Telegram(), Clock()
    results = runs([None, "HTTP 502", "HTTP 502", "HTTP 502", None, None])
    for _ in range(6):
        code = main(
            ["--state", str(state)], ENV, clock=clock, check=lambda _: next(results), post=telegram
        )
        assert code == 0
    assert len(telegram.texts) == 2
    assert telegram.texts[0] == (
        f"trainsync uptime: real is DOWN: {REAL} failed 2 checks in a row (last: HTTP 502)"
    )
    assert (
        telegram.texts[1] == f"trainsync uptime: real RECOVERED: {REAL} answers again after 45 min"
    )
    assert telegram.urls[0] == f"http://telegram.test/bot{TOKEN}/sendMessage"
    out = capsys.readouterr().out
    assert TOKEN not in out
    assert "real: HTTP 502 -> down" in out


def test_failed_send_keeps_the_state_and_fails_the_run(tmp_path: Path) -> None:
    state = tmp_path / "uptime.json"
    broken, clock = Telegram(status=500), Clock()
    args = ["--state", str(state)]
    assert main(args, ENV, clock=clock, check=lambda _: "HTTP 503", post=broken) == 0
    assert main(args, ENV, clock=clock, check=lambda _: "HTTP 503", post=broken) == 1
    assert load_state(state)["real"].status is Status.FAILING
    working = Telegram()
    assert main(args, ENV, clock=clock, check=lambda _: "HTTP 503", post=working) == 0
    assert len(working.texts) == 1
    assert "DOWN" in working.texts[0]
    # A failed recovery message is retried by the next good check too.
    assert main(args, ENV, clock=clock, check=lambda _: None, post=broken) == 1
    assert load_state(state)["real"].status is Status.DOWN
    assert main(args, ENV, clock=clock, check=lambda _: None, post=working) == 0
    assert "RECOVERED" in working.texts[-1]


def test_without_telegram_the_state_still_advances(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state, telegram = tmp_path / "uptime.json", Telegram()
    env = {"UPTIME_DEMO_URL": "https://d.ts.net:8443"}
    for _ in range(2):
        assert main(["--state", str(state)], env, check=lambda _: "HTTP 500", post=telegram) == 0
    assert load_state(state)["demo"].status is Status.DOWN
    assert telegram.texts == []
    assert "skipped (Telegram not configured)" in capsys.readouterr().out


def test_no_targets_is_a_clean_skip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--state", str(tmp_path / "s.json")], {}) == 0
    assert "nothing to check" in capsys.readouterr().out
    assert not (tmp_path / "s.json").exists()


def test_probe_reports_connection_errors() -> None:
    # Port 9 on localhost (discard) is closed in CI and on the Mac: a quick refusal, no network.
    reason = probe("http://127.0.0.1:9/health/ready")
    assert reason is not None
    assert "Error" in reason


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200 if self.path == "/ok" else 503)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        return None


def test_probe_against_a_local_server() -> None:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        assert probe(f"{base}/ok") is None
        assert probe(f"{base}/health/ready") == "HTTP 503"
    finally:
        server.shutdown()
        server.server_close()
