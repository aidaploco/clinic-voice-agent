"""Which transcriber hears a language choice on a phone line?

    uv run python scripts/choice_probe.py

The caller's answer to the language menu is a word or two: "español", "Nederlands", "bosanski",
"English", alone or with "please". This speaks those with several voices, degrades the audio to
what a phone line gives (8 kHz, narrow band, mu-law, some noise), has each candidate transcriber
hear it, and counts how often `choice.chosen_language` finds the right language in what came
back. A candidate that misses on this is not fit to listen at the menu.

Synthetic voices are an easy case: no accent, no hesitation, no handset. This ranks candidates;
it is not the rate a real caller would get. A real recording of the owner saying the words on a
phone line, run through the same candidates, is the check that counts. Costs a few cents.
"""

import argparse
import asyncio
import io
import json
import sys
import tempfile
import wave
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import aiohttp
import numpy as np
from language_probe import proper_wav, speak_deepgram, speak_openai

from clinic_voice_agent.choice import chosen_language
from clinic_voice_agent.settings import get_settings

PHRASES = {
    "en": ["English", "English, please", "In English"],
    "es": ["Español", "Español, por favor", "En español"],
    "nl": ["Nederlands", "Nederlands, alstublieft", "In het Nederlands"],
    "bs": ["Bosanski", "Bosanski, molim", "Na bosanskom"],
}
MACOS = {"en": "Alex", "es": "Paulina", "nl": "Xander", "bs": "Lana"}
KEYTERMS = ["español", "Nederlands", "bosanski", "English"]
OPENAI_PROMPT = "The caller chooses a language: English, español, Nederlands or bosanski."
DEEPGRAM_VOICES = {"en": "aura-2-thalia-en", "es": "aura-2-estrella-es", "nl": "aura-2-beatrix-nl"}


def phone_line(wav: bytes, noise_db: float = -30.0) -> bytes:
    """Make clean 16 kHz speech sound like a phone call: band-limited, 8 kHz, mu-law, noisy."""
    with wave.open(io.BytesIO(wav)) as w:
        rate = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768
    spectrum = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / rate)
    spectrum[(freqs < 300) | (freqs > 3400)] = 0
    x = np.fft.irfft(spectrum, len(x))
    x = x[:: rate // 8000]  # 8 kHz
    mu = 255.0  # mu-law: 8 bits, as the telephone network does
    x = np.clip(x / max(1e-9, np.abs(x).max()) * 0.8, -1, 1)
    coded = np.sign(x) * np.log1p(mu * np.abs(x)) / np.log1p(mu)
    coded = np.round(coded * 127) / 127
    x = np.sign(coded) * ((1 + mu) ** np.abs(coded) - 1) / mu
    x = x + np.random.default_rng(0).normal(0, 10 ** (noise_db / 20), len(x))
    x = np.repeat(x, 2)  # back to 16 kHz for the services
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return out.getvalue()


async def speak_macos(language: str, text: str) -> bytes:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "line.wav"
        process = await asyncio.create_subprocess_exec(
            "say", "-v", MACOS[language], "-o", str(path),
            "--file-format=WAVE", "--data-format=LEI16@16000", text,
        )  # fmt: skip
        await process.wait()
        return path.read_bytes()


async def deepgram_multi(http: aiohttp.ClientSession, audio: bytes, keyterms: bool) -> str:
    key = get_settings().deepgram_api_key.get_secret_value()
    url = "https://api.deepgram.com/v1/listen?model=nova-3&language=multi&smart_format=false"
    if keyterms:
        url += "".join(f"&keyterm={k}" for k in KEYTERMS)
    headers = {"Authorization": f"Token {key}", "Content-Type": "audio/wav"}
    async with http.post(url, headers=headers, data=audio) as r:
        r.raise_for_status()
        reply = await r.json()
    return reply["results"]["channels"][0]["alternatives"][0]["transcript"]


async def openai_open(http: aiohttp.ClientSession, audio: bytes, prompt: bool) -> str:
    key = get_settings().openai_api_key.get_secret_value()
    form = aiohttp.FormData()
    form.add_field("file", audio, filename="line.wav", content_type="audio/wav")
    form.add_field("model", "gpt-4o-transcribe")
    if prompt:
        form.add_field("prompt", OPENAI_PROMPT)
    async with http.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        data=form,
    ) as r:
        r.raise_for_status()
        return (await r.json())["text"]


EARS = {
    "deepgram multi": lambda h, a: deepgram_multi(h, a, False),
    "deepgram multi + keyterms": lambda h, a: deepgram_multi(h, a, True),
    "openai, no hint": lambda h, a: openai_open(h, a, False),
    "openai + names hint": lambda h, a: openai_open(h, a, True),
}


async def voices_for(http: aiohttp.ClientSession, language: str, text: str) -> dict[str, bytes]:
    out = {"macos": await speak_macos(language, text)}
    try:
        out["openai"] = await speak_openai(http, language, text)
    except Exception as error:
        print(f"  (no openai voice for {language}: {error})", file=sys.stderr)
    if language in DEEPGRAM_VOICES:
        out["deepgram"] = await speak_deepgram(http, language, text)
    return out


async def main() -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    sem = asyncio.Semaphore(6)
    rows: list[dict] = []
    async with aiohttp.ClientSession() as http:

        async def one(language, text, voice, line, quality, audio, ear):
            async with sem:
                try:
                    heard = await EARS[ear](http, audio)
                except Exception as error:
                    heard = f"<error {error}>"
            found = chosen_language(heard)
            rows.append(
                dict(
                    language=language,
                    text=text,
                    voice=voice,
                    line=line,
                    ear=ear,
                    heard=heard,
                    found=found,
                    ok=found == language,
                )  # fmt: skip
            )

        jobs = []
        for language, texts in PHRASES.items():
            for text in texts:
                for voice, wav in (await voices_for(http, language, text)).items():
                    wav = proper_wav(wav) if wav[:4] != b"RIFF" else wav
                    for quality, audio in (("clean", wav), ("phone", phone_line(wav))):
                        for ear in EARS:
                            jobs.append(one(language, text, voice, quality, quality, audio, ear))
        await asyncio.gather(*jobs)

    tally: dict = defaultdict(lambda: [0, 0])
    for r in rows:
        tally[(r["ear"], r["line"], r["language"])][0] += r["ok"]
        tally[(r["ear"], r["line"], r["language"])][1] += 1
    print("| Transcriber | Line | English | Spanish | Dutch | Bosnian | All |")
    print("|---|---|---|---|---|---|---|")
    for ear in EARS:
        for line in ("clean", "phone"):
            cells, hit, total = [], 0, 0
            for language in PHRASES:
                ok, n = tally[(ear, line, language)]
                cells.append(f"{ok}/{n}")
                hit, total = hit + ok, total + n
            print(f"| {ear} | {line} | " + " | ".join(cells) + f" | {hit}/{total} |")
    path = Path("evals/reports") / f"choice-probe-{datetime.now():%Y-%m-%dT%H%M%S}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print(f"\nevery transcript: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
