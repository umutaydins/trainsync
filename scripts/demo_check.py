"""`make demo-check` (P7.9): prove compose.demo.yml is a read-only demo with synthetic data.

1. The rendered compose config: own project name and volumes, no bot, DEMO_MODE on the app
   containers, the demo worker, Postgres/Redis/fake_strava private on an internal network, only
   the gateway published and only on 127.0.0.1; a missing DEMO_API_KEY stops compose.
2. The stack starts (its own check project and port, never the running demo), seeds itself, and
   through the gateway: reads return the seeded data, every kind of write is 403 with the demo
   message, /metrics is 404. The in-stack reset command runs again cleanly.
3. Tear down with volumes.

    uv run python scripts/demo_check.py [--keep]
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "trainsync-democheck"
PORT = 18081
BASE = f"http://127.0.0.1:{PORT}"
# A labelled check-only key: the stack lives for the length of this script, on 127.0.0.1.
API_KEY = "demo-check-only-api-key"
DEMO_DETAIL = "This is a read-only demo."
LONG_RUNNING = ("postgres", "redis", "fake-strava", "api", "worker", "gateway")
PRIVATE = ("postgres", "redis", "fake-strava")


def _env_file(lines: list[str]) -> Path:
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
        handle.write("\n".join(lines) + "\n")
    return Path(handle.name)


ENV_FILE = _env_file([f"DEMO_API_KEY={API_KEY}", f"DEMO_GATEWAY_PORT={PORT}"])


def fail(message: str) -> None:
    print(f"demo-check: FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def compose(
    *args: str, env_file: Path = ENV_FILE, project: str | None = PROJECT, check: bool = True
) -> subprocess.CompletedProcess[str]:
    command = ["docker", "compose", "--env-file", str(env_file)]
    if project:
        command += ["-p", project]
    command += ["-f", str(ROOT / "compose.demo.yml"), *args]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if check and result.returncode != 0:
        fail(f"{' '.join(args)}: {(result.stdout + result.stderr).strip()[-2000:]}")
    return result


def request(
    path: str, method: str = "GET", body: bytes | None = None, key: bool = True
) -> tuple[int, dict[str, str], bytes]:
    headers = {"X-API-Key": API_KEY} if key else {}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, method=method, data=body, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=10) as response:  # noqa: S310  (local URL)
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def check_config() -> None:
    config = json.loads(compose("config", "--format", "json", project=None).stdout)
    if config.get("name") != "trainsync-demo":
        fail(f"the project name must be trainsync-demo, got {config.get('name')}")
    services = config["services"]
    if "bot" in services or "backup" in services:
        fail("the demo runs no bot and no backups")
    for name in PRIVATE:
        if services[name].get("ports"):
            fail(f"{name} publishes a port")
        if set(services[name]["networks"]) != {"backend"}:
            fail(f"{name} must only be on the internal backend network")
    if not config["networks"]["backend"].get("internal"):
        fail("the backend network must be internal")
    published = {name: s["ports"] for name, s in services.items() if s.get("ports")}
    if set(published) != {"gateway"}:
        fail(f"only the gateway may publish a port, got {sorted(published)}")
    if any(p.get("host_ip") != "127.0.0.1" for p in published["gateway"]):
        fail("the gateway must only listen on 127.0.0.1")
    for name in ("api", "worker", "seed", "migrate"):
        if services[name]["environment"].get("DEMO_MODE") != "true":
            fail(f"{name} must run with DEMO_MODE=true")
    if "trainsync.demo.worker.DemoWorkerSettings" not in services["worker"]["command"]:
        fail("the worker must be the demo worker (reset only, no Strava sync)")
    volumes = {v.get("source") for s in services.values() for v in s.get("volumes", [])}
    if not volumes or not all(str(v).startswith("demo-") for v in volumes):
        fail(f"the demo must use its own volumes, got {sorted(map(str, volumes))}")
    for name in LONG_RUNNING:
        if services[name].get("restart") != "unless-stopped":
            fail(f"{name} must restart unless-stopped")
        if not services[name].get("mem_limit"):
            fail(f"{name} has no memory limit")
    missing = compose("config", env_file=_env_file([]), check=False)
    if missing.returncode == 0 or "set DEMO_API_KEY in .env.demo" not in missing.stderr:
        fail(f"compose started without DEMO_API_KEY: {missing.stderr.strip()}")
    print("  config: own project/volumes, no bot, DEMO_MODE, private data, gateway on 127.0.0.1")


def wait_ready() -> None:
    for _ in range(90):
        try:
            if request("/health/ready", key=False)[0] == 200:
                return
        except OSError:
            pass
        time.sleep(2)
    fail("the gateway never answered /health/ready")


def _items(path: str) -> int:
    status, _, body = request(path)
    if status != 200:
        fail(f"GET {path}: {status} {body[:300]!r}")
    return len(json.loads(body)["items"])


def check_reads() -> None:
    counts = {path: _items(path) for path in ("/v1/activities", "/v1/training/workouts")}
    if not all(counts.values()):
        fail(f"no seeded data through the gateway: {counts}")
    status, _, body = request("/v1/training/programs/active")
    if status != 200 or json.loads(body)["name"] != "Upper/Lower 4-day":
        fail(f"no active demo program: {status} {body[:300]!r}")
    if request("/v1/activities", key=False)[0] != 401:
        fail("the demo API must still require its key")
    activities, workouts = counts.values()
    print(f"  reads: {activities} activities, {workouts} workouts")


def check_writes() -> None:
    writes = [
        ("PUT", "/v1/nutrition/profile", b"{}"),
        ("POST", "/v1/training/exercises", b"{}"),
        ("DELETE", "/v1/training/programs/1", None),
        ("POST", "/webhooks/strava", b"{}"),
        ("GET", "/auth/strava/login", None),
    ]
    for method, path, body in writes:
        status, headers, raw = request(path, method, body)
        if status != 403 or json.loads(raw) != {"detail": DEMO_DETAIL}:
            fail(f"{method} {path} must be the demo 403, got {status} {raw[:200]!r}")
        if {k.lower(): v for k, v in headers.items()}.get("x-trainsync-demo") != "read-only":
            fail(f"{method} {path}: missing the x-trainsync-demo header")
    if request("/metrics", key=False)[0] != 404:
        fail("/metrics must be 404 through the gateway")
    print(f"  writes: {len(writes)} kinds refused with 403; /metrics is 404")


def check_reset() -> None:
    reset = ["python", "-m", "trainsync.demo", "exec", "python", "-m", "trainsync.demo", "reset"]
    result = compose("exec", "-T", "worker", *reset)
    if "demo reset: ResetSummary(" not in result.stdout:
        fail(f"the in-stack reset printed no summary: {result.stdout[-500:]}")
    if not _items("/v1/activities"):
        fail("no activities after the reset")
    print("  reset: the worker container wipes and re-seeds")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="leave the stack running")
    args = parser.parse_args()
    print("demo-check: config")
    check_config()
    try:
        print("demo-check: build + start")
        compose("up", "-d", "--build")
        wait_ready()
        check_reads()
        check_writes()
        check_reset()
    finally:
        if not args.keep:
            compose("down", "-v", "--remove-orphans", check=False)
    print("demo-check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
