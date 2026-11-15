"""A scripted caller who speaks real audio into a real LiveKit room.

It proves the whole voice path with nobody at a microphone: the lines are
synthesised, published into a room as if they were a phone line, and the
worker is dispatched to that room. Afterwards it prints the call's record.

    uv run python -m clinic_voice_agent.worker dev          # terminal 1
    uv run python scripts/audio_caller.py "Alex Rivera." "I need to move my appointment."

Needs LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET and ELEVENLABS_API_KEY.
Costs a few cents per run.
"""

import asyncio
import json
import os
import secrets
import sys
import time
from pathlib import Path

import aiohttp
from dotenv import load_dotenv
from livekit import api, rtc

from clinic_voice_agent.settings import get_settings
from clinic_voice_agent.worker import WORKER_NAME

SAMPLE_RATE = 16000
FRAME = SAMPLE_RATE // 50  # 20 ms of samples
SILENCE = b"\x00\x00" * FRAME
CALLER_VOICE = "EXAVITQu4vr4xnSDxMaL"


async def synthesise(http: aiohttp.ClientSession, text: str) -> bytes:
    key = get_settings().elevenlabs_api_key.get_secret_value()
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{CALLER_VOICE}"
    async with http.post(
        url,
        params={"output_format": f"pcm_{SAMPLE_RATE}"},
        headers={"xi-api-key": key},
        json={"text": text, "model_id": "eleven_flash_v2_5"},
    ) as response:
        response.raise_for_status()
        return await response.read()


async def microphone(source: rtc.AudioSource, speech: asyncio.Queue[bytes]) -> None:
    """Feed the track continuously: queued speech when there is some, silence otherwise."""
    pending = b""
    while True:
        while not speech.empty():
            pending += speech.get_nowait()
        chunk, pending = pending[: len(SILENCE)], pending[len(SILENCE) :]
        chunk = chunk.ljust(len(SILENCE), b"\x00") if chunk else SILENCE
        await source.capture_frame(rtc.AudioFrame(chunk, SAMPLE_RATE, 1, FRAME))


class AgentWatch:
    """Follows the agent's published state: listening, thinking or speaking."""

    def __init__(self, room: rtc.Room) -> None:
        self.room = room

    def state(self) -> str | None:
        for participant in self.room.remote_participants.values():
            if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT:
                return participant.attributes.get("lk.agent.state")
        return None

    async def has_finished_a_turn(self, timeout: float = 40.0) -> float:
        """Wait for the agent to speak and then go quiet. Returns seconds until it began."""
        began = time.monotonic()
        started_after = None
        quiet_since = None
        state = None
        while time.monotonic() - began < timeout:
            if not self.room.isconnected():
                return started_after or 0.0
            state = self.state()
            if state == "speaking":
                started_after = started_after or time.monotonic() - began
                quiet_since = None
            elif started_after is not None and state == "listening":
                quiet_since = quiet_since or time.monotonic()
                if time.monotonic() - quiet_since > 1.0:
                    return started_after
            await asyncio.sleep(0.05)
        raise TimeoutError(
            f"the agent did not finish a turn within {timeout:.0f}s (state: {state})"
        )


async def main(lines: list[str]) -> int:
    load_dotenv()
    room_name = f"test-{secrets.token_hex(4)}"
    token = (
        api.AccessToken()
        .with_identity("scripted-caller")
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )
    room = rtc.Room()
    await room.connect(os.environ["LIVEKIT_URL"], token)
    source = rtc.AudioSource(SAMPLE_RATE, 1)
    track = rtc.LocalAudioTrack.create_audio_track("microphone", source)
    await room.local_participant.publish_track(
        track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    )
    speech: asyncio.Queue[bytes] = asyncio.Queue()
    mic = asyncio.create_task(microphone(source, speech))

    lk = api.LiveKitAPI()
    await lk.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(agent_name=WORKER_NAME, room=room_name)
    )
    await lk.aclose()
    print(f"room {room_name}: agent dispatched", flush=True)

    watch = AgentWatch(room)
    waits: list[float] = []
    try:
        await watch.has_finished_a_turn()  # the greeting
        async with aiohttp.ClientSession() as http:
            for line in lines:
                if not room.isconnected():
                    break
                audio = await synthesise(http, line)
                speech.put_nowait(audio)
                await asyncio.sleep(len(audio) / (2 * SAMPLE_RATE))  # while the line is spoken
                waits.append(await watch.has_finished_a_turn())
    finally:
        mic.cancel()
        if room.isconnected():
            await room.disconnect()

    await asyncio.sleep(4)  # the worker writes the record when the call closes
    records = sorted(get_settings().recordings_dir.glob(f"*{room_name}.json"))
    if not records:
        print("no call record was written", file=sys.stderr)
        return 1
    record = json.loads(Path(records[-1]).read_text())
    for line in record["transcript"]:
        print(f"{line['speaker']:>6}: {line['text']}")
    print("actions:", [a["action"] for a in record["actions"]])
    print("appointment after:", record["appointment_after"])
    print(
        "latency (s):", {k: (v["median"], v["max"]) for k, v in record["latency_seconds"].items()}
    )
    print("seconds from end of caller's line to agent speaking:", [round(w, 2) for w in waits])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
