"""Samples of ways to make a voice say "rođenja" with the long, stressed e.

    uv run python scripts/pronunciation_samples.py

The voices read "datum rođenja" with a short e. A text-to-speech service takes plain text, so the
options are to respell the word, or to say in its instructions where the stress falls. This makes
one sentence each way, for the owner to listen to; she picks, and the winner goes in `locales.py`.
"""

import asyncio
import sys
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

from clinic_voice_agent.settings import get_settings
from clinic_voice_agent.voice import SPEAKING_STYLE

OUT = Path("evals/reports/bs-voices")
SENTENCE = "Koji je vaš datum {word}? Molim vas, recite dan, mjesec i godinu."
VARIANTS = {
    "a-plain": ("rođenja", SPEAKING_STYLE["bs"]),
    "b-ee": ("rođeenja", SPEAKING_STYLE["bs"]),
    "c-eee": ("rođeeenja", SPEAKING_STYLE["bs"]),
    "d-macron": ("rođēnja", SPEAKING_STYLE["bs"]),
    "e-told": (
        "rođenja",
        SPEAKING_STYLE["bs"]
        + " In the word rođenja, the stress is on the e after the đ and that e is long, like"
        " rođeeenja.",
    ),
}
VOICES = ["coral", "shimmer", "nova"]


async def one(http, key, voice, name, word, style) -> None:
    body = {"model": "gpt-4o-mini-tts", "voice": voice, "input": SENTENCE.format(word=word),
            "instructions": style, "response_format": "mp3"}  # fmt: skip
    async with http.post("https://api.openai.com/v1/audio/speech",
                         headers={"Authorization": f"Bearer {key}"}, json=body) as r:  # fmt: skip
        r.raise_for_status()
        (OUT / f"rodjenja-{name}-{voice}.mp3").write_bytes(await r.read())


async def main() -> int:
    load_dotenv()
    OUT.mkdir(parents=True, exist_ok=True)
    key = get_settings().openai_api_key.get_secret_value()
    async with aiohttp.ClientSession() as http:
        await asyncio.gather(
            *(one(http, key, v, n, w, s) for v in VOICES for n, (w, s) in VARIANTS.items())
        )
    print(f"{len(VOICES) * len(VARIANTS)} samples in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
