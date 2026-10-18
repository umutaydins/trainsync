"""External uptime check (P7.8, ADR 0027): `GET /health/ready` from outside the Mac, with a
small alert state machine so one outage sends one "down" and one "recovered" message.

    PYTHONPATH=src python3 -m trainsync.ops.uptime --state uptime-state.json

Run by `.github/workflows/uptime.yml` every 15 minutes. Targets come from the environment:
`UPTIME_URL` (the real backend) and `UPTIME_DEMO_URL` (the demo); an empty one is skipped.
Telegram goes through `trainsync.ops.alert` (TELEGRAM_BOT_TOKEN + TELEGRAM_NOTIFY_CHAT_ID from
the environment, so the token never appears on a command line).

The machine, per target (docs/diagrams.md §24):

    up --fail--> failing(1) --fail--> down (send "down")      --ok--> up (send "recovered")
       <--ok----            <-- ...    down --fail--> down (nothing)

`failing(n)` with n < threshold sends nothing, so a flapping target (fail, ok, fail, ok) never
alerts. A message that could not be sent leaves the state where it was, so the next run tries
again. Standard library only: the workflow runs it with the runner's python3, no install.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from trainsync.ops.alert import Post, send

DEFAULT_THRESHOLD = 2
TIMEOUT_S = 15.0
READY_PATH = "/health/ready"
TARGET_ENV = (("real", "UPTIME_URL"), ("demo", "UPTIME_DEMO_URL"))

Clock = Callable[[], datetime]
# (url) -> None when healthy, else a short reason ("HTTP 503", "URLError: ...").
Probe = Callable[[str], str | None]


class Status(StrEnum):
    UP = "up"
    FAILING = "failing"
    DOWN = "down"


class Message(StrEnum):
    NONE = "none"
    DOWN = "down"
    RECOVERED = "recovered"


@dataclass(frozen=True, slots=True)
class TargetState:
    status: Status = Status.UP
    failures: int = 0  # consecutive failed checks
    since: datetime | None = None  # first failure of the current failing/down streak

    def to_json(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "failures": self.failures,
            "since": self.since.isoformat() if self.since else None,
        }

    @classmethod
    def from_json(cls, data: object) -> "TargetState":
        """Anything unreadable is a fresh `up`: a lost state costs at most one repeated alert."""
        if not isinstance(data, dict):
            return cls()
        try:
            status = Status(data.get("status", "up"))
            failures = int(data.get("failures", 0))
            since_raw = data.get("since")
            since = datetime.fromisoformat(since_raw) if isinstance(since_raw, str) else None
        except (TypeError, ValueError):
            return cls()
        return cls(status, max(0, failures), since)


def step(
    state: TargetState, ok: bool, now: datetime, threshold: int = DEFAULT_THRESHOLD
) -> tuple[TargetState, Message]:
    """The next state and the message to send for one check result (pure)."""
    if ok:
        message = Message.RECOVERED if state.status is Status.DOWN else Message.NONE
        return TargetState(), message
    failures = state.failures + 1
    since = state.since or now
    if state.status is Status.DOWN:
        return TargetState(Status.DOWN, failures, since), Message.NONE
    if failures >= threshold:
        return TargetState(Status.DOWN, failures, since), Message.DOWN
    return TargetState(Status.FAILING, failures, since), Message.NONE


def load_state(path: Path) -> dict[str, TargetState]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(name): TargetState.from_json(value) for name, value in data.items()}


def save_state(path: Path, states: Mapping[str, TargetState]) -> None:
    payload = {name: state.to_json() for name, state in sorted(states.items())}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def probe(url: str) -> str | None:
    request = urllib.request.Request(url, method="GET")  # noqa: S310  (https URL from settings)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        return f"HTTP {exc.code}"
    except OSError as exc:  # URLError, TLS errors and timeouts
        return f"{type(exc).__name__}: {exc}"
    return None if 200 <= status < 300 else f"HTTP {status}"


def targets(env: Mapping[str, str]) -> dict[str, str]:
    found = {}
    for name, variable in TARGET_ENV:
        base = env.get(variable, "").strip().rstrip("/")
        if base:
            found[name] = base + READY_PATH
    return found


def _minutes(start: datetime | None, now: datetime) -> str:
    if start is None:
        return ""
    return f" after {max(0, round((now - start).total_seconds() / 60))} min"


def text(
    name: str, url: str, message: Message, state: TargetState, now: datetime, reason: str
) -> str:
    if message is Message.DOWN:
        return (
            f"trainsync uptime: {name} is DOWN: {url} failed {state.failures} checks in a row "
            f"(last: {reason})"
        )
    return f"trainsync uptime: {name} RECOVERED: {url} answers again{_minutes(state.since, now)}"


@dataclass(frozen=True, slots=True)
class Outcome:
    states: dict[str, TargetState]
    lines: list[str]
    send_failed: bool


def run(
    checks: Mapping[str, str],
    states: Mapping[str, TargetState],
    env: Mapping[str, str],
    *,
    now: datetime,
    check: Probe = probe,
    post: Post | None = None,
    threshold: int = DEFAULT_THRESHOLD,
) -> Outcome:
    new_states = dict(states)
    lines: list[str] = []
    send_failed = False
    for name, url in checks.items():
        old = states.get(name, TargetState())
        reason = check(url)
        new, message = step(old, reason is None, now, threshold)
        lines.append(f"{name}: {'ok' if reason is None else reason} -> {new.status.value}")
        if message is not Message.NONE:
            # The recovery text needs the outage start, which only the old state still has.
            body = text(
                name, url, message, new if message is Message.DOWN else old, now, reason or ""
            )
            sent = send(body, env) if post is None else send(body, env, post)
            if sent is False:
                send_failed = True
                lines.append(f"{name}: Telegram send failed; state kept, the next run retries")
                # Keep the streak (so the next failure fires again), but not the transition.
                new = replace(new, status=Status.FAILING) if message is Message.DOWN else old
            else:
                result = "sent" if sent else "skipped (Telegram not configured)"
                lines.append(f"{name}: {message.value} alert {result}")
        new_states[name] = new
    return Outcome(new_states, lines, send_failed)


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    *,
    clock: Clock = lambda: datetime.now(UTC),
    check: Probe = probe,
    post: Post | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="External uptime check with Telegram alerts")
    parser.add_argument(
        "--state", type=Path, required=True, help="JSON state file (kept between runs)"
    )
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    args = parser.parse_args(argv)
    environ = os.environ if env is None else env
    checks = targets(environ)
    if not checks:
        print("uptime: UPTIME_URL and UPTIME_DEMO_URL are not set; nothing to check")
        return 0
    outcome = run(
        checks,
        load_state(args.state),
        environ,
        now=clock(),
        check=check,
        post=post,
        threshold=max(1, args.threshold),
    )
    save_state(args.state, outcome.states)
    for line in outcome.lines:
        print(f"uptime: {line}")
    # A target being down is reported by Telegram, not by a red run (GitHub would e-mail every
    # 15 minutes); a failed alert is red, because then nobody would hear about it.
    return 1 if outcome.send_failed else 0


if __name__ == "__main__":
    sys.exit(main())
