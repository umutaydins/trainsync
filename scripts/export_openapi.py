"""Write the API's OpenAPI document to docs/openapi.json.

Run: `uv run python scripts/export_openapi.py` (or `--check` to fail when the file is stale).
The spec does not depend on configuration, so placeholder settings are enough.
"""

import json
import sys
from pathlib import Path

from cryptography.fernet import Fernet

from trainsync.core.settings import Settings
from trainsync.main import create_app

OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"


def render() -> str:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        strava_client_id="0",
        strava_client_secret="placeholder",  # noqa: S106
        strava_webhook_verify_token="placeholder",  # noqa: S106
        token_encryption_key=Fernet.generate_key().decode(),
        state_signing_key="placeholder",
        api_keys="placeholder",
    )
    spec = create_app(settings).openapi()
    return json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != content:
            print(f"{OUTPUT} is stale; run: uv run python scripts/export_openapi.py")
            return 1
        return 0
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
