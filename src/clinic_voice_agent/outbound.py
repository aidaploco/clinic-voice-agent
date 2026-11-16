"""Emily calling out: the sequence, and every refusal along it.

This is the one place the project can ring a phone, so it is built to refuse first:

1. Only a number from `ALLOWED_NUMBERS` is ever dialled. A request names no number of its own;
   if there are several allowed, it may only choose among them. An empty list dials nobody.
2. The day's cap applies, and a trunk must be configured.
3. Emily goes into the room first, and the phone is not rung until she is there. If no worker is
   running (or the one running is busy), nothing is dialled.
4. The phone is rung with a ring limit and a maximum length, and the room is removed if nobody
   answers.

It talks to LiveKit through a client passed in, so every step is tested without a phone.
"""

import asyncio
import json
import logging
import secrets
import time
from datetime import datetime
from typing import Any

from google.protobuf.duration_pb2 import Duration
from livekit import api

from clinic_voice_agent.limits import calls_today
from clinic_voice_agent.settings import Settings

logger = logging.getLogger(__name__)

AGENT = 4  # rtc.ParticipantKind.PARTICIPANT_KIND_AGENT


class OutboundRefused(Exception):
    """A reason not to dial, with the HTTP status the page server should answer with."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def choose_number(allowed: frozenset[str], requested: str | None = None) -> str:
    """The number to dial: one of the allowed ones, never one the caller of the API supplied."""
    if not allowed:
        raise OutboundRefused(409, "ALLOWED_NUMBERS is empty, so nobody may be called")
    if requested is None:
        if len(allowed) > 1:
            raise OutboundRefused(400, "more than one number is allowed; say which one")
        return next(iter(allowed))
    if requested not in allowed:
        raise OutboundRefused(403, "that number is not allowed")
    return requested


def dial_request(
    settings: Settings, number: str, room: str, identity: str
) -> api.CreateSIPParticipantRequest:
    """The call to LiveKit that rings the phone. Built here so a test can check every limit."""
    if not settings.sip_outbound_trunk_id:
        raise OutboundRefused(503, "SIP_OUTBOUND_TRUNK_ID is not set")
    return api.CreateSIPParticipantRequest(
        sip_trunk_id=settings.sip_outbound_trunk_id,
        sip_call_to=number,
        room_name=room,
        participant_identity=identity,
        participant_name="Phone",
        ringing_timeout=Duration(seconds=settings.ring_seconds),
        max_call_duration=Duration(seconds=settings.max_call_seconds),
        wait_until_answered=True,  # the request returns only once someone has picked up
        hide_phone_number=False,  # the worker reads the number to check it
    )


async def agent_joined(lk: Any, room: str, wait: float) -> bool:
    """Whether a worker has joined the room within `wait` seconds."""
    deadline = time.monotonic() + wait
    while True:
        response = await lk.room.list_participants(api.ListParticipantsRequest(room=room))
        if any(p.kind == AGENT for p in response.participants):
            return True
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(0.4)


async def call_the_owner(
    lk: Any, settings: Settings, requested: str | None = None, now: datetime | None = None
) -> str:
    """Dial the owner's phone and return the room's id. Raises `OutboundRefused` otherwise."""
    number = choose_number(settings.allowed_set, requested)
    if not settings.sip_outbound_trunk_id:
        raise OutboundRefused(503, "SIP_OUTBOUND_TRUNK_ID is not set")
    if calls_today(settings.recordings_dir, now or datetime.now()) >= settings.daily_call_cap:
        raise OutboundRefused(429, "the day's call cap is reached")

    token = secrets.token_hex(4)
    room, identity = f"phone-out-{token}", f"phone-out-{token}"
    await lk.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(
            agent_name=settings.agent_name,
            room=room,
            metadata=json.dumps({"direction": "outbound"}),
        )
    )
    if not await agent_joined(lk, room, settings.agent_wait_seconds):
        await _remove(lk, room)
        raise OutboundRefused(
            503, "no worker joined the room, so the phone was not rung (is the worker running?)"
        )
    try:
        await lk.sip.create_sip_participant(dial_request(settings, number, room, identity))
    except Exception as problem:
        await _remove(lk, room)
        raise OutboundRefused(
            504, f"the call was not answered or could not be placed ({type(problem).__name__})"
        ) from None
    return room


async def _remove(lk: Any, room: str) -> None:
    try:
        await lk.room.delete_room(api.DeleteRoomRequest(room=room))
    except Exception:
        # An empty room expires by itself, and this must never mask the real refusal.
        logger.warning("could not remove the room after a refused call", exc_info=True)


def direction_of(metadata: str | None) -> str:
    """ "outbound" when the dispatch says so, otherwise "inbound". Anything unreadable is inbound,
    which is the stricter case: the caller's number is checked against the allowlist."""
    try:
        value = json.loads(metadata or "")
    except ValueError:
        return "inbound"
    return (
        "outbound"
        if isinstance(value, dict) and value.get("direction") == "outbound"
        else "inbound"
    )
