"""fake_strava as a real HTTP server (uvicorn subprocess), for tests that need real sockets:
other processes calling it, or real httpx timeouts."""

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@contextmanager
def run_fake_strava(**config: str | int) -> Iterator[str]:
    """Start fake_strava with `FAKE_STRAVA_<KEY>=<value>` for each config item; yields its URL."""
    port = free_port()
    env = {**os.environ, **{f"FAKE_STRAVA_{k.upper()}": str(v) for k, v in config.items()}}
    proc = subprocess.Popen(  # noqa: S603  (fixed args, our own interpreter)
        [
            sys.executable,
            "-m",
            "uvicorn",
            "fake_strava.app:create_app",
            "--factory",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_until_up(url, proc)
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _wait_until_up(url: str, proc: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("fake_strava exited during startup")
        try:
            httpx.get(f"{url}/_control/config", timeout=1).raise_for_status()
            return
        except httpx.TransportError:
            time.sleep(0.1)
    raise RuntimeError("fake_strava did not start")
