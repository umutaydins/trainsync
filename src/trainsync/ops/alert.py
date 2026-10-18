"""Send one operational alert to Telegram; a no-op when Telegram is not configured.

    python3 -m trainsync.ops.alert "backup failed: ..."

Reads TELEGRAM_BOT_TOKEN and the chat from TELEGRAM_NOTIFY_CHAT_ID (else the first of
TELEGRAM_ALLOWED_CHAT_IDS), like the app's notifier. Standard library only, so the backup image
and host-side scripts (P7.8) can use it. Exits 0 when sent or skipped, 1 when the send failed:
an alert must never be the reason a backup is marked failed, so callers usually ignore it.
"""

import json
import os
import sys
import urllib.request
from collections.abc import Callable, Mapping, Sequence

DEFAULT_API_BASE = "https://api.telegram.org"
TIMEOUT_S = 10.0

Post = Callable[[str, bytes], int]


def _post(url: str, body: bytes) -> int:
    request = urllib.request.Request(  # noqa: S310  (https URL built from settings)
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310
        return int(response.status)


def chat_id(env: Mapping[str, str]) -> str | None:
    explicit = env.get("TELEGRAM_NOTIFY_CHAT_ID", "").strip()
    if explicit:
        return explicit
    allowed = [c.strip() for c in env.get("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",")]
    return next((c for c in allowed if c), None)


def send(text: str, env: Mapping[str, str], post: Post = _post) -> bool | None:
    """True when sent, False when the send failed, None when Telegram is not configured."""
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = chat_id(env)
    if not token or chat is None:
        return None
    base = env.get("TELEGRAM_API_BASE_URL", "").strip() or DEFAULT_API_BASE
    body = json.dumps({"chat_id": chat, "text": text, "disable_web_page_preview": True}).encode()
    try:
        return post(f"{base}/bot{token}/sendMessage", body) == 200
    except OSError:  # URLError, HTTPError and timeouts are all OSErrors
        return False


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    post: Post = _post,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python3 -m trainsync.ops.alert MESSAGE", file=sys.stderr)
        return 2
    result = send(" ".join(args), os.environ if env is None else env, post)
    if result is None:
        print("alert: Telegram not configured, skipped")
        return 0
    # Never print the URL: it contains the bot token.
    if not result:
        print("alert: Telegram send failed", file=sys.stderr)
        return 1
    print("alert: sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
