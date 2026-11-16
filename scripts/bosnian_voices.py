"""Make samples of candidate Bosnian voices, for the owner to listen to.

    uv run python scripts/bosnian_voices.py

Writes evals/reports/bs-voices/<candidate>-<n>.<ext> for three of Emily's Bosnian lines.
A word error rate says nothing about how a voice sounds, and the owner is the only judge of
Bosnian here, so this makes things to listen to and prints which candidates worked.
"""

import asyncio
import os
import sys
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

from clinic_voice_agent.locales import locale_of

OUT = Path("evals/reports/bs-voices")
ELEVEN_VOICES = {  # premade voices that exist for every account
    "sarah": "EXAVITQu4vr4xnSDxMaL",
    "charlotte": "XB0fDUnXU5powFXDhCwa",
    "lily": "pFZP5JQG7iQjIQuC4Bku",
    "jessica": "cgSgspJ2msm6clMCkdW9",
}
ELEVEN_MODELS = ["eleven_multilingual_v2", "eleven_v3", "eleven_flash_v2_5"]
OPENAI_VOICES = ["coral", "shimmer", "sage", "nova", "ballad"]
OPENAI_STYLE = (
    "Speak Bosnian as a native speaker from Sarajevo would, in a warm, relaxed, natural "
    "conversational tone, like a friendly receptionist chatting on the phone. Not formal, not "
    "slow, with natural rhythm and intonation. Do not read it like an announcement."
)


def lines() -> list[str]:
    lc = locale_of("bs")
    return [
        lc.ask_dob,
        (
            "Mogu vam ponuditi srijedu u pola jedanaest ujutro, ili četvrtak u pola pet "
            "poslijepodne. Koji vam odgovara?"
        ),
        lc.deaf_goodbye,
    ]


async def eleven(http, key, voice_id, model, text) -> bytes:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
    body = {"text": text, "model_id": model}
    async with http.post(url, headers={"xi-api-key": key}, json=body) as r:
        if r.status != 200:
            raise RuntimeError(f"{r.status} {(await r.text())[:160]}")
        return await r.read()


async def openai(http, key, voice, text) -> bytes:
    body = {"model": "gpt-4o-mini-tts", "voice": voice, "input": text, "instructions": OPENAI_STYLE,
            "response_format": "mp3"}  # fmt: skip
    async with http.post("https://api.openai.com/v1/audio/speech",
                         headers={"Authorization": f"Bearer {key}"}, json=body) as r:  # fmt: skip
        r.raise_for_status()
        return await r.read()


async def main() -> int:
    load_dotenv()
    OUT.mkdir(parents=True, exist_ok=True)
    ek, ok = os.environ.get("ELEVENLABS_API_KEY", ""), os.environ["OPENAI_API_KEY"]
    jobs: dict[str, object] = {}
    async with aiohttp.ClientSession() as http:
        for n, text in enumerate(lines(), 1):
            for voice in OPENAI_VOICES:
                jobs[f"openai-{voice}-{n}"] = openai(http, ok, voice, text)
            if ek:
                for model in ELEVEN_MODELS:
                    for name, vid in ELEVEN_VOICES.items():
                        jobs[f"eleven-{model.removeprefix('eleven_')}-{name}-{n}"] = eleven(
                            http, ek, vid, model, text
                        )
        results = await asyncio.gather(*jobs.values(), return_exceptions=True)
    failed: dict[str, str] = {}
    for name, result in zip(jobs, results, strict=True):
        if isinstance(result, Exception):
            failed[name.rsplit("-", 1)[0]] = str(result)
        else:
            (OUT / f"{name}.mp3").write_bytes(result)
    print(f"{len(jobs) - len(failed) * 3} samples in {OUT}")
    for name, why in failed.items():
        print(f"  failed: {name}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
