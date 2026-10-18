"""Manage Strava's webhook (push) subscription for this API application (P7.7).

    uv run python scripts/strava-subscription.py view
    uv run python scripts/strava-subscription.py create [--callback-url URL]
    uv run python scripts/strava-subscription.py delete [ID]

Credentials come from the env file (default `.env.prod`; `--env-file` to change it):
STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_WEBHOOK_VERIFY_TOKEN. The callback defaults to
`$PUBLIC_API_BASE_URL/webhooks/strava`; Strava calls it (GET with `hub.challenge`) before
answering `create`, so the stack must be up and reachable through Funnel. Strava allows one
subscription per application. Every call goes through trainsync's Strava client (retries,
timeouts, logging without secrets).
"""

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

from trainsync.core.settings import Settings
from trainsync.strava.client import StravaClient
from trainsync.strava.errors import (
    StravaAuthError,
    StravaError,
    StravaNotFound,
    StravaRequestError,
)
from trainsync.strava.http import build_http_client

ROOT = Path(__file__).resolve().parents[1]


def env_value(env_file: Path, name: str) -> str:
    """The last `NAME=value` in the env file (quotes stripped), or empty."""
    if not env_file.is_file():
        return ""
    value = ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
    return value


def load_settings(env_file: Path) -> Settings:
    if not env_file.is_file():
        raise SystemExit(f"strava-subscription: {env_file} not found (see .env.prod.example)")
    return Settings(_env_file=env_file)  # type: ignore[call-arg]  # values come from the file


async def run(args: argparse.Namespace, http: httpx.AsyncClient | None = None) -> int:
    settings = load_settings(args.env_file)
    own_http = http is None
    client_http = http or build_http_client(settings)
    strava = StravaClient(client_http, settings)
    try:
        return await _command(args, settings, strava)
    except StravaError as exc:
        print(f"strava-subscription: {_explain(args.command, exc)}", file=sys.stderr)
        return 1
    finally:
        if own_http:
            await client_http.aclose()


async def _command(args: argparse.Namespace, settings: Settings, strava: StravaClient) -> int:
    if args.command == "view":
        subscriptions = await strava.list_push_subscriptions()
        if not subscriptions:
            print("no subscription")
        for sub in subscriptions:
            print(f"id={sub.id} callback_url={sub.callback_url} created_at={sub.created_at}")
        return 0
    if args.command == "create":
        return await _create(args, settings, strava)
    subscription_id = args.id or settings.strava_webhook_subscription_id
    if subscription_id is None:
        listed = await strava.list_push_subscriptions()
        if len(listed) != 1:
            print("strava-subscription: give the id to delete (see `view`)", file=sys.stderr)
            return 2
        subscription_id = listed[0].id
    await strava.delete_push_subscription(subscription_id)
    print(f"deleted subscription id={subscription_id}")
    print(f"remove STRAVA_WEBHOOK_SUBSCRIPTION_ID from {args.env_file.name}")
    return 0


async def _create(args: argparse.Namespace, settings: Settings, strava: StravaClient) -> int:
    """Strava answers 200 or 201 on success (both are fine). On a 4xx it explains itself in the
    body; "already exists" is answered with the existing subscription from a `view` call."""
    callback = args.callback_url or _default_callback(args.env_file)
    try:
        sub = await strava.create_push_subscription(
            callback, settings.strava_webhook_verify_token.get_secret_value()
        )
    except StravaRequestError as exc:
        _print_refusal(exc)
        if any("already exists" in error.code for error in exc.errors):
            return await _existing(args, strava, callback)
        raise
    print(f"created subscription id={sub.id} for {callback}")
    _print_env_line(args.env_file, sub.id)
    return 0


def _print_refusal(exc: StravaRequestError) -> None:
    print(
        f"strava-subscription: Strava answered {exc.status_code}: {exc.message or '(no message)'}",
        file=sys.stderr,
    )
    for error in exc.errors:
        print(f"  {error}", file=sys.stderr)


async def _existing(args: argparse.Namespace, strava: StravaClient, callback: str) -> int:
    listed = await strava.list_push_subscriptions()
    if not listed:
        print("strava-subscription: but `view` lists none; try again in a minute", file=sys.stderr)
        return 1
    for sub in listed:
        print(f"already subscribed: id={sub.id} callback_url={sub.callback_url}")
        _print_env_line(args.env_file, sub.id)
    if all(sub.callback_url == callback for sub in listed):
        return 0
    print(
        f"strava-subscription: the existing callback is not {callback}; `delete` it, then "
        "`create` again",
        file=sys.stderr,
    )
    return 1


def _print_env_line(env_file: Path, subscription_id: int) -> None:
    print(f"put this in {env_file.name}:")
    print(f"STRAVA_WEBHOOK_SUBSCRIPTION_ID={subscription_id}")
    print("then: scripts/mac-prod.sh up   (recreates the containers with the new value)")


def _default_callback(env_file: Path) -> str:
    base = env_value(env_file, "PUBLIC_API_BASE_URL").rstrip("/")
    if not base:
        raise SystemExit(
            "strava-subscription: set PUBLIC_API_BASE_URL in the env file or pass --callback-url"
        )
    return f"{base}/webhooks/strava"


def _explain(command: str, exc: StravaError) -> str:
    if isinstance(exc, StravaNotFound):
        return "no such subscription (see `view`)"
    if isinstance(exc, StravaRequestError) and command == "create" and exc.status_code == 400:
        return (
            "Strava refused the subscription (400): either one already exists (`view`, then "
            "`delete`), or Strava could not verify the callback URL. Check that the stack is up, "
            "Funnel is on, and GET <callback>?hub.mode=subscribe&hub.challenge=x"
            "&hub.verify_token=<token> answers from outside."
        )
    if isinstance(exc, StravaAuthError) or (
        isinstance(exc, StravaRequestError) and exc.status_code == 403
    ):
        return "Strava rejected the client id / secret"
    return str(exc)


def parser() -> argparse.ArgumentParser:
    parse = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parse.add_argument("--env-file", type=Path, default=ROOT / ".env.prod")
    commands = parse.add_subparsers(dest="command", required=True)
    commands.add_parser("view", help="show the subscription")
    create = commands.add_parser("create", help="subscribe this backend to Strava webhooks")
    create.add_argument("--callback-url", help="default: $PUBLIC_API_BASE_URL/webhooks/strava")
    delete = commands.add_parser("delete", help="remove the subscription")
    delete.add_argument("id", nargs="?", type=int, help="default: the one in the env file")
    return parse


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
