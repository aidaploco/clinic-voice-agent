"""Does the Bosnian transcriber get a spoken date of birth right?

    uv run python scripts/dob_probe.py

The natural ways to say 14 March 1990 in Bosnian, spoken by two voices, on a clean line and a
phone-degraded one, transcribed with each candidate setup; a transcript is right if it holds
the day, the month and the year 1990. Synthetic voices: this ranks setups, not callers.
"""

import asyncio
import re
import sys
from collections import defaultdict

import aiohttp
from choice_probe import phone_line, speak_macos
from language_probe import proper_wav, speak_openai

from clinic_voice_agent.settings import get_settings

SAYINGS = [
    "Četrnaesti mart hiljadu devetsto devedesete.",
    "Rođen sam četrnaestog marta hiljadu devetsto devedesete.",
    "Četrnaestog marta hiljadu devetsto devedesete.",
    "Četrnaest mart hiljadu devetsto devedeset.",
]
HINTS = {
    "current hint": "Razgovor na bosanskom jeziku. Pišite latinicom.",
    "no hint": None,
    "dates hint": (
        "Razgovor na bosanskom jeziku, latinicom. Datum rođenja, na primjer: "
        "dvadeseti juni hiljadu devetsto osamdeset pete."
    ),
}


async def hear(http, audio: bytes, hint: str | None, model: str) -> str:
    form = aiohttp.FormData()
    form.add_field("file", audio, filename="line.wav", content_type="audio/wav")
    form.add_field("model", model)
    form.add_field("language", "bs")
    if hint:
        form.add_field("prompt", hint)
    key = get_settings().openai_api_key.get_secret_value()
    async with http.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        data=form,
    ) as r:
        r.raise_for_status()
        return (await r.json())["text"]


def right(text: str) -> bool:
    t = text.lower()
    day = "14" in t or "četrnaest" in t or "cetrnaest" in t
    month = "mart" in t or "marta" in t or ".3." in t
    return bool(day and month and re.search(r"1990|devedesete?\b", t) and "1997" not in t)


async def main() -> int:
    tally = defaultdict(lambda: [0, 0])
    misses = []
    async with aiohttp.ClientSession() as http:
        for text in SAYINGS:
            clips = {
                "macos": await speak_macos("bs", text),
                "openai": await speak_openai(http, "bs", text),
            }
            for voice, wav in clips.items():
                wav = wav if wav[:4] == b"RIFF" else proper_wav(wav)
                for line, audio in (("clean", wav), ("phone", phone_line(wav))):
                    for model in ("gpt-4o-transcribe", "gpt-4o-mini-transcribe"):
                        for name, hint in HINTS.items():
                            heard = await hear(http, audio, hint, model)
                            ok = right(heard)
                            cell = tally[(model, name, line)]
                            cell[0] += ok
                            cell[1] += 1
                            if not ok and line == "phone":
                                misses.append((model, name, voice, text, heard))
    print("| Model | Hint | Clean | Phone |\n|---|---|---|---|")
    for model in ("gpt-4o-transcribe", "gpt-4o-mini-transcribe"):
        for name in HINTS:
            c, p = tally[(model, name, "clean")], tally[(model, name, "phone")]
            print(f"| {model} | {name} | {c[0]}/{c[1]} | {p[0]}/{p[1]} |")
    for miss in misses[:12]:
        print("  miss:", *miss, sep=" | ")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
