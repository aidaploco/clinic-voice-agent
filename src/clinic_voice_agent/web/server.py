"""A local server for the browser page: serves it, mints call tokens, returns finished records.

Run it with `uv run python -m clinic_voice_agent.web`. Outside a container it listens on
127.0.0.1 only; in one, compose publishes its port on the host's 127.0.0.1 only. It refuses
requests that do not name a local host, so a web page elsewhere cannot use it to start calls
on the owner's account.
"""

import asyncio
import json
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from aiohttp import web
from livekit import api

from clinic_voice_agent.limits import calls_today
from clinic_voice_agent.settings import Settings, get_settings

# Long enough to join, short enough that a leaked token is useless by the time it matters.
TOKEN_LIFETIME = timedelta(minutes=5)
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
SETTINGS = web.AppKey("settings", Settings)
ROOM_NAME = re.compile(r"^web-[0-9a-f]{8}$")


def find_record(folder: Path, room: str) -> dict | None:
    found = sorted(folder.glob(f"*{room}.json")) if folder.is_dir() else []
    return json.loads(found[-1].read_text()) if found else None


def new_room_name() -> str:
    return f"web-{secrets.token_hex(4)}"


def mint_token(settings: Settings, room: str, identity: str) -> str:
    """A token for one caller in one room. Joining it also dispatches Emily to the room."""
    if settings.livekit_api_key is None or settings.livekit_api_secret is None:
        raise RuntimeError("LIVEKIT_API_KEY and LIVEKIT_API_SECRET are not set")
    return (
        api.AccessToken(
            settings.livekit_api_key.get_secret_value(),
            settings.livekit_api_secret.get_secret_value(),
        )
        .with_identity(identity)
        .with_ttl(TOKEN_LIFETIME)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=False,
            )
        )
        .with_room_config(
            api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=settings.agent_name)])
        )
        .to_jwt()
    )


def host_is_local(host_header: str) -> bool:
    """Whether the Host header names this machine. A rebinding attack arrives under another name."""
    host = host_header.strip().lower()
    name = host.split("]")[0] + "]" if host.startswith("[") else host.split(":")[0]
    return name in LOCAL_HOSTS


@web.middleware
async def local_only(request: web.Request, handler):
    if not host_is_local(request.headers.get("Host", "")):
        raise web.HTTPForbidden(text="this server answers on localhost only")
    origin = request.headers.get("Origin")
    if origin and request.method == "POST":
        # A page from another site must not be able to start a call from here.
        own = f"{request.scheme}://{request.headers.get('Host', '')}"
        if origin != own:
            raise web.HTTPForbidden(text="cross-origin request refused")
    return await handler(request)


async def token(request: web.Request) -> web.Response:
    settings: Settings = request.app[SETTINGS]
    if calls_today(settings.recordings_dir, datetime.now()) >= settings.daily_call_cap:
        raise web.HTTPTooManyRequests(text="the day's call cap is reached")
    room = new_room_name()
    identity = f"caller-{secrets.token_hex(4)}"
    try:
        jwt = mint_token(settings, room, identity)
    except RuntimeError as problem:
        raise web.HTTPServiceUnavailable(text=str(problem)) from None
    if settings.livekit_url is None:
        raise web.HTTPServiceUnavailable(text="LIVEKIT_URL is not set")
    return web.json_response({"url": settings.livekit_url, "token": jwt, "room": room})


async def call_record(request: web.Request) -> web.Response:
    """The finished record of a call, or 404 until the worker has written it."""
    room = request.match_info["room"]
    if not ROOM_NAME.match(room):
        raise web.HTTPBadRequest(text="not a room name from this page")
    record = await asyncio.to_thread(find_record, request.app[SETTINGS].recordings_dir, room)
    if record is None:
        raise web.HTTPNotFound(text="not written yet")
    return web.json_response(record)


NOT_BUILT = (
    "The page has not been built. In another terminal: cd web && npm ci && npm run build "
    "(or `npm run dev` for development, which serves the page on http://127.0.0.1:5173)."
)


async def index(request: web.Request) -> web.StreamResponse:
    page = request.app[SETTINGS].web_dist / "index.html"
    if not await asyncio.to_thread(page.is_file):
        raise web.HTTPServiceUnavailable(text=NOT_BUILT)
    return web.FileResponse(page)


def make_app(settings: Settings | None = None) -> web.Application:
    app = web.Application(middlewares=[local_only])
    app[SETTINGS] = settings or get_settings()
    app.router.add_get("/", index)
    app.router.add_post("/api/token", token)
    app.router.add_get("/api/calls/{room}", call_record)
    assets = app[SETTINGS].web_dist / "assets"
    if assets.is_dir():
        app.router.add_static("/assets/", assets)
    return app


def main() -> None:
    settings = get_settings()
    web.run_app(make_app(settings), host=settings.web_host, port=settings.web_port)
