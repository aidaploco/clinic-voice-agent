"""A scripted caller who speaks real audio into a real LiveKit room.

It proves the whole voice path with nobody at a microphone: the lines are
synthesised, published into a room as if they were a phone line, and the
worker is dispatched to that room. Afterwards it prints the call's record.

    uv run python -m clinic_voice_agent.worker start        # terminal 1
    uv run python scripts/audio_caller.py "Alex Rivera." "March 14th, 1990." \\
        "I need to move my appointment."

Needs LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET. On a Mac the caller's
voice is the built-in one, so a run costs only what the agent's side costs.
"""

import asyncio
import json
import os
import secrets
import shutil
import sys
import tempfile
import time
import wave
from pathlib import Path

import aiohttp
from dotenv import load_dotenv
from livekit import api, rtc

from clinic_voice_agent.settings import get_settings
from clinic_voice_agent.worker import WORKER_NAME

SAMPLE_RATE = 24000
FRAME = SAMPLE_RATE // 50  # 20 ms of samples
SILENCE = b"\x00\x00" * FRAME


async def synthesise(http: aiohttp.ClientSession, text: str) -> bytes:
    """The line as 24 kHz mono speech.

    On a Mac the built-in voice is used: it is local and costs nothing, so
    test runs do not spend a speech provider's credit. Elsewhere, OpenAI.
    """
    if sys.platform == "darwin" and shutil.which("say"):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "line.wav"
            process = await asyncio.create_subprocess_exec(
                "say", "-o", str(path), "--file-format=WAVE",
                f"--data-format=LEI16@{SAMPLE_RATE}", text,
            )  # fmt: skip
            await process.wait()
            with wave.open(str(path)) as audio:
                return audio.readframes(audio.getnframes())
    key = get_settings().openai_api_key.get_secret_value()
    async with http.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": "gpt-4o-mini-tts",
            "voice": "alloy",
            "input": text,
            "response_format": "pcm",
        },
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
    # A shallow queue: the default holds a second of audio ahead, which delays the speech
    # by a second and inflates every wait this script measures.
    source = rtc.AudioSource(SAMPLE_RATE, 1, queue_size_ms=100)
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

    # What the caller felt, per line: its speech ends -> the agent's state turns to speaking.
    print("reply_waits", json.dumps([round(wait, 3) for wait in waits]), flush=True)

    # The worker writes the record once the call has fully closed, which can
    # take a while after the caller leaves.
    records: list[Path] = []
    for _ in range(90):
        records = sorted(get_settings().recordings_dir.glob(f"*{room_name}.json"))
        if records:
            break
        await asyncio.sleep(0.5)
    if not records:
        print("no call record was written", file=sys.stderr)
        return 1
    record = json.loads(Path(records[-1]).read_text())
    for line in record["transcript"]:
        print(f"{line['speaker']:>6}: {line['text']}")
    for event in record["audit"]:
        print(f"  gateway: {event['operation']:<16} {event['outcome']:<8} {event['reason']}")
    for check in record["checks"]:
        print(f"  review:  {check['name']:<24} {check['verdict']:<8} {check['detail']}")
    print("appointment after:", record["appointment_after"])
    print("ended because:", record["ended_because"], "| errors:", record["errors"])
    for stage, numbers in record["latency_seconds"].items():
        print(f"  {stage:<16} median {numbers['median']:.2f}s  worst {numbers['max']:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
