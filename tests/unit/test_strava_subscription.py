"""P7.7: scripts/strava-subscription.py against a respx fake of Strava's push subscription API."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest
import respx

from tests.conftest import TEST_ENV

ROOT = Path(__file__).resolve().parents[2]
API = "http://strava.test/api/v3"
SUBS = f"{API}/push_subscriptions"


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "strava_subscription", ROOT / "scripts" / "strava-subscription.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["strava_subscription"] = module
    spec.loader.exec_module(module)
    return module


script = _script()


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    values = {
        **TEST_ENV,
        "STRAVA_API_BASE_URL": API,
        "PUBLIC_API_BASE_URL": "https://mac.tail1234.ts.net/",
        "STRAVA_WEBHOOK_SUBSCRIPTION_ID": "",
    }
    path = tmp_path / ".env.prod"
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    return path


async def run(env_file: Path, *argv: str) -> int:
    args = script.parser().parse_args(["--env-file", str(env_file), *argv])
    async with httpx.AsyncClient() as http:
        result: int = await script.run(args, http)
    return result


@pytest.mark.parametrize("status", [200, 201])
@respx.mock
async def test_create_uses_the_public_callback_and_app_credentials(
    env_file: Path, capsys: pytest.CaptureFixture[str], status: int
) -> None:
    route = respx.post(SUBS).mock(return_value=httpx.Response(status, json={"id": 4242}))
    assert await run(env_file, "create") == 0
    form = dict(httpx.QueryParams(route.calls[0].request.content.decode()))
    assert form == {
        "client_id": TEST_ENV["STRAVA_CLIENT_ID"],
        "client_secret": TEST_ENV["STRAVA_CLIENT_SECRET"],
        "callback_url": "https://mac.tail1234.ts.net/webhooks/strava",
        "verify_token": TEST_ENV["STRAVA_WEBHOOK_VERIFY_TOKEN"],
    }
    out = capsys.readouterr().out
    assert "created subscription id=4242" in out
    assert "\nSTRAVA_WEBHOOK_SUBSCRIPTION_ID=4242\n" in out  # a line to paste as is
    assert TEST_ENV["STRAVA_CLIENT_SECRET"] not in out


@respx.mock
async def test_create_with_an_explicit_callback(env_file: Path) -> None:
    route = respx.post(SUBS).mock(return_value=httpx.Response(201, json={"id": 1}))
    assert (
        await run(env_file, "create", "--callback-url", "https://other.example/webhooks/strava")
        == 0
    )
    assert b"other.example" in route.calls[0].request.content


@respx.mock
async def test_create_refused_explains_both_reasons(
    env_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    respx.post(SUBS).mock(return_value=httpx.Response(400, json={"message": "Bad Request"}))
    assert await run(env_file, "create") == 1
    err = capsys.readouterr().err
    assert "already exists" in err
    assert "verify the callback URL" in err


CALLBACK = "https://mac.tail1234.ts.net/webhooks/strava"


def refusal(code: str, field: str = "callback url") -> httpx.Response:
    body = {
        "message": "Bad Request",
        "errors": [{"resource": "PushSubscription", "field": field, "code": code}],
    }
    return httpx.Response(400, json=body)


@respx.mock
async def test_create_prints_stravas_error_body(
    env_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    respx.post(SUBS).mock(return_value=refusal("not verifiable"))
    assert await run(env_file, "create") == 1
    err = capsys.readouterr().err
    assert "Strava answered 400: Bad Request" in err
    assert "resource=PushSubscription field=callback url code=not verifiable" in err
    assert TEST_ENV["STRAVA_CLIENT_SECRET"] not in err


@pytest.mark.parametrize(("existing", "code"), [(CALLBACK, 0), ("https://old.example/x", 1)])
@respx.mock
async def test_create_when_one_already_exists_shows_its_id(
    env_file: Path, capsys: pytest.CaptureFixture[str], existing: str, code: int
) -> None:
    respx.post(SUBS).mock(return_value=refusal("already exists", field=""))
    respx.get(SUBS).mock(
        return_value=httpx.Response(200, json=[{"id": 377572, "callback_url": existing}])
    )
    assert await run(env_file, "create") == code
    captured = capsys.readouterr()
    assert "code=already exists" in captured.err
    assert f"already subscribed: id=377572 callback_url={existing}" in captured.out
    assert "\nSTRAVA_WEBHOOK_SUBSCRIPTION_ID=377572\n" in captured.out
    assert ("delete` it" in captured.err) is (code == 1)


@respx.mock
async def test_bad_credentials(env_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    respx.get(SUBS).mock(return_value=httpx.Response(401))
    assert await run(env_file, "view") == 1
    assert "client id / secret" in capsys.readouterr().err


@respx.mock
async def test_view_lists_or_says_none(env_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    route = respx.get(SUBS).mock(
        side_effect=[
            httpx.Response(200, json=[]),
            httpx.Response(
                200,
                json=[
                    {
                        "id": 7,
                        "callback_url": "https://x/webhooks/strava",
                        "created_at": "2026-10-18T10:00:00Z",
                    }
                ],
            ),
        ]
    )
    assert await run(env_file, "view") == 0
    assert await run(env_file, "view") == 0
    out = capsys.readouterr().out
    assert "no subscription" in out
    assert "id=7 callback_url=https://x/webhooks/strava" in out
    assert route.calls[0].request.url.params["client_id"] == TEST_ENV["STRAVA_CLIENT_ID"]


@respx.mock
async def test_delete_by_id_from_the_listing_or_404(
    env_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    respx.get(SUBS).mock(return_value=httpx.Response(200, json=[{"id": 7}]))
    deleted = respx.delete(f"{SUBS}/7").mock(return_value=httpx.Response(204))
    assert await run(env_file, "delete") == 0  # the only one listed
    assert deleted.called
    respx.delete(f"{SUBS}/8").mock(return_value=httpx.Response(404))
    assert await run(env_file, "delete", "8") == 1
    assert "no such subscription" in capsys.readouterr().err


@respx.mock
async def test_delete_without_a_single_candidate_asks_for_the_id(env_file: Path) -> None:
    respx.get(SUBS).mock(return_value=httpx.Response(200, json=[]))
    assert await run(env_file, "delete") == 2


@pytest.fixture
def env_without_public_url(env_file: Path) -> Path:
    text = env_file.read_text(encoding="utf-8").replace("PUBLIC_API_BASE_URL=", "UNUSED=")
    env_file.write_text(text, encoding="utf-8")
    return env_file


async def test_missing_env_file(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="not found"):
        await run(tmp_path / "missing.env", "view")


async def test_create_needs_a_public_url(env_without_public_url: Path) -> None:
    with pytest.raises(SystemExit, match="PUBLIC_API_BASE_URL"):
        await run(env_without_public_url, "create")
