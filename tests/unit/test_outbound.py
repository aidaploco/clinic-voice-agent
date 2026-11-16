import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec

import pytest
from livekit import api
from livekit.api.agent_dispatch_service import AgentDispatchService
from livekit.api.room_service import RoomService
from livekit.api.sip_service import SipService
from pydantic import SecretStr

from clinic_voice_agent.outbound import (
    OutboundRefused,
    agent_joined,
    call_the_owner,
    choose_number,
    dial_request,
)
from clinic_voice_agent.settings import Settings

OWNER = "+14155550123"
OTHER = "+14155550199"


def settings(tmp_path, **more) -> Settings:
    values = {
        "allowed_numbers": OWNER,
        "sip_outbound_trunk_id": "ST_out",
        "recordings_dir": tmp_path,
        "agent_name": "clinic-receptionist",
        "agent_wait_seconds": 1.0,
        "ring_seconds": 30,
        "max_call_seconds": 300,
        "daily_call_cap": 25,
        "livekit_api_key": SecretStr("k"),
        "livekit_api_secret": SecretStr("s" * 40),
    } | more
    return Settings(_env_file=None, **values)


def fake_livekit(agent_present_after: int | None = 0):
    """A LiveKit client whose services have the real signatures, so a wrong call is a TypeError.

    `agent_present_after`: the agent shows up in the room from this many polls on; None: never.
    """
    lk = SimpleNamespace(
        room=create_autospec(RoomService, instance=True),
        sip=create_autospec(SipService, instance=True),
        agent_dispatch=create_autospec(AgentDispatchService, instance=True),
    )
    polls = {"n": 0}

    async def list_participants(request):
        polls["n"] += 1
        present = agent_present_after is not None and polls["n"] > agent_present_after
        kind = 4 if present else 0
        return SimpleNamespace(participants=[SimpleNamespace(kind=kind)] if present else [])

    lk.room.list_participants = AsyncMock(side_effect=list_participants)
    return lk


def nothing_was_dialled(lk) -> bool:
    return lk.sip.create_sip_participant.await_count == 0


@pytest.mark.parametrize(
    "allowed,requested,status",
    [
        (frozenset(), None, 409),
        (frozenset({OWNER, OTHER}), None, 400),
        (frozenset({OWNER}), OTHER, 403),
        (frozenset({OWNER}), "+19995550000", 403),
    ],
)
def test_a_number_is_chosen_only_from_the_allowed_ones(allowed, requested, status):
    with pytest.raises(OutboundRefused) as refused:
        choose_number(allowed, requested)
    assert refused.value.status == status


def test_the_only_allowed_number_is_dialled_and_a_request_may_only_pick_among_allowed_ones():
    assert choose_number(frozenset({OWNER})) == OWNER
    assert choose_number(frozenset({OWNER, OTHER}), OTHER) == OTHER


def test_the_dial_request_carries_every_limit(tmp_path):
    request = dial_request(settings(tmp_path), OWNER, "phone-out-aaaaaaaa", "phone-out-aaaaaaaa")
    assert request.sip_trunk_id == "ST_out" and request.sip_call_to == OWNER
    assert request.room_name == "phone-out-aaaaaaaa" and request.wait_until_answered is True
    assert request.ringing_timeout.seconds == 30 and request.max_call_duration.seconds == 300
    assert request.hide_phone_number is False


def test_a_dial_request_without_a_trunk_is_refused(tmp_path):
    with pytest.raises(OutboundRefused) as refused:
        dial_request(settings(tmp_path, sip_outbound_trunk_id=None), OWNER, "r", "i")
    assert refused.value.status == 503


async def test_the_agent_is_waited_for_and_found():
    assert await agent_joined(fake_livekit(agent_present_after=2), "r", wait=2.0) is True
    assert await agent_joined(fake_livekit(agent_present_after=None), "r", wait=0.0) is False


async def test_the_phone_is_rung_only_after_the_agent_is_in_the_room(tmp_path):
    lk = fake_livekit(agent_present_after=1)
    order = []
    lk.agent_dispatch.create_dispatch = AsyncMock(side_effect=lambda r: order.append("dispatch"))
    lk.sip.create_sip_participant = AsyncMock(side_effect=lambda r: order.append("dial"))
    room = await call_the_owner(lk, settings(tmp_path))
    assert order == ["dispatch", "dial"] and room.startswith("phone-out-")
    dispatch = lk.agent_dispatch.create_dispatch.await_args.args[0]
    assert dispatch.agent_name == "clinic-receptionist" and dispatch.room == room
    assert json.loads(dispatch.metadata) == {"direction": "outbound"}
    dialled = lk.sip.create_sip_participant.await_args.args[0]
    assert dialled.sip_call_to == OWNER and dialled.room_name == room


async def test_when_no_worker_joins_the_phone_is_never_rung_and_the_room_is_removed(tmp_path):
    lk = fake_livekit(agent_present_after=None)
    with pytest.raises(OutboundRefused) as refused:
        await call_the_owner(lk, settings(tmp_path))
    assert refused.value.status == 503 and "worker" in refused.value.message
    assert nothing_was_dialled(lk)
    lk.room.delete_room.assert_awaited_once()


async def test_a_call_that_is_not_answered_removes_the_room_and_says_so(tmp_path):
    lk = fake_livekit()
    lk.sip.create_sip_participant = AsyncMock(side_effect=RuntimeError("ringing timeout"))
    with pytest.raises(OutboundRefused) as refused:
        await call_the_owner(lk, settings(tmp_path))
    assert refused.value.status == 504 and OWNER not in refused.value.message
    lk.room.delete_room.assert_awaited_once()


async def test_a_failure_to_remove_the_room_does_not_hide_the_real_refusal(tmp_path):
    lk = fake_livekit(agent_present_after=None)
    lk.room.delete_room = AsyncMock(side_effect=RuntimeError("already gone"))
    with pytest.raises(OutboundRefused) as refused:
        await call_the_owner(lk, settings(tmp_path))
    assert refused.value.status == 503


@pytest.mark.parametrize(
    "more,status",
    [({"allowed_numbers": ""}, 409), ({"sip_outbound_trunk_id": None}, 503)],
)
async def test_nothing_is_dispatched_or_dialled_when_a_precondition_fails(tmp_path, more, status):
    lk = fake_livekit()
    with pytest.raises(OutboundRefused) as refused:
        await call_the_owner(lk, settings(tmp_path, **more))
    assert refused.value.status == status
    assert nothing_was_dialled(lk) and lk.agent_dispatch.create_dispatch.await_count == 0


async def test_the_days_cap_stops_a_call_before_anything_happens(tmp_path):
    (tmp_path / f"{datetime.now():%Y-%m-%d}T100000-web-aaaaaaaa.json").write_text("{}")
    lk = fake_livekit()
    with pytest.raises(OutboundRefused) as refused:
        await call_the_owner(lk, settings(tmp_path, daily_call_cap=1))
    assert refused.value.status == 429
    assert nothing_was_dialled(lk) and lk.agent_dispatch.create_dispatch.await_count == 0


def test_the_sdk_still_offers_the_options_this_module_relies_on():
    fields = {f.name for f in api.CreateSIPParticipantRequest.DESCRIPTOR.fields}
    assert {"ringing_timeout", "max_call_duration", "wait_until_answered", "sip_call_to"} <= fields


@pytest.mark.parametrize(
    "metadata,direction",
    [
        ('{"direction": "outbound"}', "outbound"),
        ('{"direction": "inbound"}', "inbound"),
        ('{"direction": "OUTBOUND"}', "inbound"),
        ("[1, 2]", "inbound"),
        ("not json", "inbound"),
        ("", "inbound"),
        (None, "inbound"),
    ],
)
def test_the_direction_is_outbound_only_when_the_dispatch_says_so_exactly(metadata, direction):
    from clinic_voice_agent.outbound import direction_of

    assert direction_of(metadata) == direction


def test_an_outbound_call_opens_by_saying_who_is_calling_and_reveals_nothing_about_the_patient():
    from clinic_voice_agent.flow import GREETING, OUTBOUND_GREETING, opening_line

    assert opening_line("inbound") == GREETING and opening_line("outbound") == OUTBOUND_GREETING
    assert "calling about an appointment" in OUTBOUND_GREETING
    assert "Emily" in OUTBOUND_GREETING and "automated" in OUTBOUND_GREETING
    for private in ("Okafor", "Rivera", "3:30", "three thirty", "shoulder", "tomorrow", "Alex"):
        assert private not in OUTBOUND_GREETING
