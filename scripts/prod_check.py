"""`make prod-check` (P7.1): prove compose.prod.yml is safe to expose, with dummy secrets.

1. The committed gateway Caddyfile matches deploy/gateway/routes.toml.
2. The rendered compose config: Postgres and Redis publish nothing and sit on an internal network;
   only the gateway publishes a port, on 127.0.0.1; every long-running service restarts and has a
   memory limit.
3. A missing secret stops compose before anything starts, and the app itself exits with a message
   that names the variable.
4. The stack starts (own project name and port), then a curl matrix built from routes.toml: every
   allowlisted route is forwarded, everything else is 404; body limit, auth rate limit and
   security headers hold.
5. The gateway's logs (access and error) never show the webhook query string (Strava's
   hub.verify_token) or an X-API-Key value.

    uv run python scripts/prod_check.py [--keep]
"""

import argparse
import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_gateway import CADDYFILE, load, render

ROOT = Path(__file__).resolve().parents[1]
DUMMY_ENV = ROOT / "deploy" / "prod-check.env"
# A labelled dummy Fernet key, built here so no key-shaped string sits in the repo.
DUMMY_FERNET_KEY = base64.urlsafe_b64encode(b"dev-only-fernet-key-not-for-use!").decode()


def _env_file() -> Path:
    # The backup service bind-mounts an existing directory; never the real iCloud folder here.
    backups = Path(tempfile.mkdtemp(prefix="prodcheck-backups-"))
    backups.chmod(0o777)  # written by the backup image's postgres user on Linux
    text = DUMMY_ENV.read_text(encoding="utf-8") + f"TOKEN_ENCRYPTION_KEY={DUMMY_FERNET_KEY}\n"
    text += f"BACKUP_HOST_DIR={backups}\n"
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
        handle.write(text)
    return Path(handle.name)


ENV_FILE = _env_file()
PROJECT = "trainsync-prodcheck"
BASE = "http://127.0.0.1:18080"
LONG_RUNNING = ("postgres", "redis", "api", "worker", "bot", "gateway", "backup")


def fail(message: str) -> None:
    print(f"prod-check: FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def compose(
    *args: str, env_file: Path = ENV_FILE, check: bool = True
) -> subprocess.CompletedProcess[str]:
    command = ["docker", "compose", "--env-file", str(env_file), "-p", PROJECT]
    command += ["-f", str(ROOT / "compose.prod.yml"), *args]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if check and result.returncode != 0:
        fail(f"{' '.join(args)}: {result.stderr.strip()[-2000:]}")
    return result


def request(
    path: str,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str]]:
    req = urllib.request.Request(  # noqa: S310  (local URL)
        BASE + path, method=method, data=body, headers=headers or {}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:  # noqa: S310  (local URL)
            return response.status, dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def check_config() -> None:
    if CADDYFILE.read_text(encoding="utf-8") != render():
        fail("deploy/gateway/Caddyfile is stale: uv run python scripts/render_gateway.py")
    config = json.loads(compose("config", "--format", "json").stdout)
    services = config["services"]
    for name in ("postgres", "redis"):
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
    for name in LONG_RUNNING:
        if services[name].get("restart") != "unless-stopped":
            fail(f"{name} must restart unless-stopped")
        if not services[name].get("mem_limit"):
            fail(f"{name} has no memory limit")
    worker_mounts = services["worker"].get("volumes", [])
    if not any(v.get("target") == "/backups" for v in worker_mounts) or not all(
        v.get("read_only") for v in worker_mounts
    ):
        fail("the worker must see the backup folder at /backups, read-only (P7.8 alerts)")
    print(
        "  config: private Postgres/Redis, gateway on 127.0.0.1 only, restarts, memory limits,"
        " read-only backup folder in the worker"
    )


def check_missing_secret() -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
        handle.write(
            "\n".join(line for line in lines if not line.startswith("TOKEN_ENCRYPTION_KEY"))
        )
    result = compose("config", env_file=Path(handle.name), check=False)
    Path(handle.name).unlink()
    if result.returncode == 0 or "set TOKEN_ENCRYPTION_KEY in .env.prod" not in result.stderr:
        fail(f"compose started without TOKEN_ENCRYPTION_KEY: {result.stderr.strip()}")
    script = "unset TOKEN_ENCRYPTION_KEY; exec uvicorn trainsync.main:create_app --factory"
    result = compose("run", "--rm", "--no-deps", "api", "sh", "-c", script, check=False)
    output = result.stdout + result.stderr
    if result.returncode == 0 or "TOKEN_ENCRYPTION_KEY (missing)" not in output:
        fail(f"the api did not exit with a clear message: {output.strip()[-1500:]}")
    print("  missing secret: compose refuses, the app exits naming TOKEN_ENCRYPTION_KEY")


def wait_ready() -> None:
    for _ in range(60):
        try:
            if request("/health/ready")[0] == 200:
                return
        except OSError:
            pass
        time.sleep(2)
    fail("the gateway never answered /health/ready")


def check_routes() -> None:
    gateway = load()
    for route in gateway.routes:
        if route.when_env:
            continue  # off unless set; its probe is in the blocked list
        status, _ = request(route.probe)
        if status == 404:
            fail(f"{route.name}: {route.probe} is not forwarded")
    for path in gateway.blocked_probes:
        status, _ = request(path)
        if status != 404:
            fail(f"{path} must be 404 through the gateway, got {status}")
    forwarded = len(gateway.routes) - 1
    print(f"  routes: {forwarded} forwarded, {len(gateway.blocked_probes)} blocked (404)")

    status, headers = request("/health/live")
    lowered = {k.lower(): v for k, v in headers.items()}
    if status != 200 or lowered.get("x-content-type-options") != "nosniff" or "server" in lowered:
        fail(f"security headers missing on /health/live: {headers}")
    status, _ = request("/webhooks/strava", "POST", b"x" * 100_000)
    if status != 413:
        fail(f"a 100 KB webhook body must be 413, got {status}")
    opener = urllib.request.build_opener(NoRedirect)
    statuses = []
    for _ in range(25):
        try:
            statuses.append(opener.open(BASE + "/auth/strava/login", timeout=10).status)
        except urllib.error.HTTPError as exc:
            statuses.append(exc.code)
    if 429 not in statuses:
        fail(f"25 quick /auth requests were never rate limited: {sorted(set(statuses))}")
    print("  headers, 64 KB webhook body limit and the /auth rate limit hold")


def _dummy(key: str) -> str:
    for line in DUMMY_ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    fail(f"{key} missing from {DUMMY_ENV.name}")
    return ""


def check_logs() -> None:
    token = _dummy("STRAVA_WEBHOOK_VERIFY_TOKEN")
    api_key = "prodcheck-log-canary-key"
    query = f"hub.mode=subscribe&hub.verify_token={token}&hub.challenge=prodcheck-challenge"
    status, _ = request(f"/webhooks/strava?{query}")
    if status != 200:
        fail(f"the webhook handshake through the gateway must be 200, got {status}")
    request("/v1/sync/status", headers={"X-API-Key": api_key})  # 401: only the log matters
    time.sleep(1)
    logs = compose("logs", "--no-color", "gateway").stdout
    if '"uri":"/webhooks/strava"' not in logs:
        fail("no access log line for /webhooks/strava: is the gateway logging?")
    for secret in (token, "hub.verify_token", "prodcheck-challenge", api_key):
        if secret in logs:
            fail(f"the gateway log contains {secret!r}")
    print("  gateway logs: no webhook query string, no API key")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="leave the stack running")
    args = parser.parse_args()
    print("prod-check: config")
    check_config()
    try:
        print("prod-check: build")
        compose("build")
        check_missing_secret()
        print("prod-check: start")
        compose("--profile", "migrate", "run", "--rm", "migrate")
        compose("up", "-d")
        wait_ready()
        check_routes()
        check_logs()
    finally:
        if not args.keep:
            compose("--profile", "migrate", "down", "-v", "--remove-orphans", check=False)
    print("prod-check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
