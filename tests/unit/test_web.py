import json
from datetime import datetime

import jwt
import pytest
from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from clinic_voice_agent.settings import Settings
from clinic_voice_agent.web.server import host_is_local, make_app, mint_token

KEY, SECRET = "devkey", "s" * 40


def settings(tmp_path, **more) -> Settings:
    return Settings(
        _env_file=None,
        livekit_url="wss://example.livekit.cloud",
        livekit_api_key=SecretStr(KEY),
        livekit_api_secret=SecretStr(SECRET),
        recordings_dir=tmp_path,
        **more,
    )


def test_a_token_joins_one_room_expires_soon_and_dispatches_the_agent(tmp_path):
    token = mint_token(settings(tmp_path), "web-0a1b2c3d", "caller-1")
    claims = jwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_aud": False})
    assert claims["video"]["room"] == "web-0a1b2c3d" and claims["video"]["roomJoin"] is True
    assert claims["video"].get("canPublishData") is False
    assert claims["exp"] - claims["nbf"] <= 5 * 60
    assert claims["roomConfig"]["agents"][0]["agentName"] == "clinic-receptionist"
    assert claims["sub"] == "caller-1"


def test_a_token_cannot_be_made_without_the_livekit_secret(tmp_path, monkeypatch):
    for name in ("LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError):
        mint_token(Settings(_env_file=None, recordings_dir=tmp_path), "web-0a1b2c3d", "x")


@pytest.mark.parametrize(
    "host,local",
    [
        ("127.0.0.1:8765", True),
        ("localhost:8765", True),
        ("[::1]:8765", True),
        ("evil.example:8765", False),
        ("127.0.0.1.evil.example", False),
        ("", False),
    ],
)
def test_only_local_host_names_are_accepted(host, local):
    assert host_is_local(host) is local


async def client(tmp_path, **more):
    test_client = TestClient(TestServer(make_app(settings(tmp_path, **more))))
    await test_client.start_server()
    return test_client


async def test_the_token_endpoint_gives_a_fresh_room_each_time(tmp_path):
    c = await client(tmp_path)
    try:
        one = await (await c.post("/api/token")).json()
        two = await (await c.post("/api/token")).json()
        assert one["room"] != two["room"] and one["url"] == "wss://example.livekit.cloud"
        assert one["room"].startswith("web-") and one["token"]
    finally:
        await c.close()


async def test_a_request_under_another_host_name_is_refused(tmp_path):
    c = await client(tmp_path)
    try:
        assert (await c.post("/api/token", headers={"Host": "evil.example"})).status == 403
    finally:
        await c.close()


async def test_a_page_from_another_site_cannot_start_a_call(tmp_path):
    c = await client(tmp_path)
    try:
        refused = await c.post("/api/token", headers={"Origin": "https://evil.example"})
        assert refused.status == 403
    finally:
        await c.close()


async def test_no_token_is_given_once_the_days_cap_is_reached(tmp_path):
    (tmp_path / f"{datetime.now():%Y-%m-%d}T100000-test-x.json").write_text("{}")
    c = await client(tmp_path, daily_call_cap=1)
    try:
        assert (await c.post("/api/token")).status == 429
    finally:
        await c.close()


async def test_a_record_is_served_only_for_a_call_id_that_cannot_be_a_path(tmp_path):
    (tmp_path / "2026-11-15T100000-web-0a1b2c3d.json").write_text(json.dumps({"ok": True}))
    c = await client(tmp_path)
    try:
        assert (await c.get("/api/calls/web-0a1b2c3d")).status == 200
        assert (await c.get("/api/calls/web-ffffffff")).status == 404
        assert (await c.get("/api/calls/..%2Fsecrets")).status in (400, 404)
        assert (
            await c.get("/api/calls/a.b")
        ).status == 400  # no dots: nothing that looks like a path
        assert (await c.get("/api/calls/console")).status == 404  # a valid id with no record
    finally:
        await c.close()


async def test_the_built_page_is_served_and_a_missing_build_says_how_to_make_one(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>page</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    c = await client(tmp_path, web_dist=dist)
    try:
        assert "<title>page</title>" in await (await c.get("/")).text()
        assert (await c.get("/assets/app.js")).status == 200
    finally:
        await c.close()

    c = await client(tmp_path, web_dist=tmp_path / "not-built")
    try:
        missing = await c.get("/")
        assert missing.status == 503 and "npm run build" in await missing.text()
    finally:
        await c.close()


def test_defaults_do_not_depend_on_the_folder_a_command_is_run_from(tmp_path, monkeypatch):
    from clinic_voice_agent.settings import PROJECT_ROOT

    monkeypatch.chdir(tmp_path)  # nowhere near the project, as when started from web/
    settings = Settings(_env_file=None)
    assert settings.web_dist == PROJECT_ROOT / "web" / "dist"
    assert settings.recordings_dir == PROJECT_ROOT / "recordings"
    assert (PROJECT_ROOT / "pyproject.toml").is_file()


async def test_the_call_list_endpoint_returns_summaries_newest_first_and_is_local_only(tmp_path):
    for started, call_id in (
        ("2026-11-15T10:00:00", "web-11111111"),
        ("2026-11-15T12:00:00", "phone-aaaaaaaaaa"),
    ):
        record = {
            "room": call_id,
            "started": started,
            "transcript": [{"speaker": "caller", "text": "x"}],
        }
        (tmp_path / f"{started.replace(':', '')}-{call_id}.json").write_text(json.dumps(record))
    c = await client(tmp_path)
    try:
        body = await (await c.get("/api/calls")).json()
        assert [x["id"] for x in body["calls"]] == ["phone-aaaaaaaaaa", "web-11111111"]
        assert "transcript" not in body["calls"][0]
        assert (await c.get("/api/calls?limit=1")).status == 200
        assert (await c.get("/api/calls?limit=lots")).status == 400
        assert (await c.get("/api/calls", headers={"Host": "evil.example"})).status == 403
        one = await (await c.get("/api/calls/phone-aaaaaaaaaa")).json()
        assert one["transcript"][0]["text"] == "x"
    finally:
        await c.close()
