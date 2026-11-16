"""Measure which speech services handle which language, by round trip.

    uv run python scripts/language_probe.py                 # every language, every pair
    uv run python scripts/language_probe.py --only bs,nl    # some languages
    uv run python scripts/language_probe.py --tts openai    # one speaking service

For each language the receptionist's sentences (evals/languages.yaml) are spoken by a
text-to-speech service, transcribed by a speech-to-text service, and the transcript is scored
against the text (word error rate: 0.0 is perfect). Every speaking service is paired with every
transcribing one, so a bad score can be traced to the side at fault: a voice that mumbles is bad
with both transcribers, a transcriber that mishears is bad with both voices.

It also keeps the audio (evals/reports/language-samples/) for a native speaker to listen to: a
word error rate says nothing about how a voice sounds.

Clean synthetic audio is an easy case. A real caller on a phone line, with an accent, is harder.
This ranks services; it does not predict a call. Costs a few cents of speech and transcription.
"""

import argparse
import asyncio
import io
import json
import statistics
import sys
import tempfile
import time
import wave
from datetime import datetime
from pathlib import Path

import aiohttp
import yaml

from clinic_voice_agent.languages import LANGUAGES
from clinic_voice_agent.settings import get_settings
from clinic_voice_agent.wer import word_error_rate

HERE = Path(__file__).parent.parent / "evals"
SAMPLES = HERE / "reports" / "language-samples"

# The Aura-2 voices that exist for each language, from Deepgram's own model list (none for Bosnian).
DEEPGRAM_VOICES = {"en": "aura-2-thalia-en", "es": "aura-2-estrella-es", "nl": "aura-2-beatrix-nl"}


async def speak_deepgram(http: aiohttp.ClientSession, lang: str, text: str) -> bytes:
    key = get_settings().deepgram_api_key.get_secret_value()
    url = (
        f"https://api.deepgram.com/v1/speak?model={DEEPGRAM_VOICES[lang]}"
        "&encoding=linear16&container=wav&sample_rate=16000"
    )
    async with http.post(url, headers={"Authorization": f"Token {key}"}, json={"text": text}) as r:
        r.raise_for_status()
        return proper_wav(await r.read())


def proper_wav(audio: bytes, rate: int = 16000) -> bytes:
    """Rewrite a WAV whose header does not state its length (a streamed one) as a complete one.

    Deepgram's `container=wav` output is of that kind; another service refuses it with a 400.
    """
    pcm = audio[44:] if audio[:4] == b"RIFF" else audio
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


# Local voices, a measuring aid only (not something the product could ship). Croatian is close
# enough to Bosnian to read the same Latin-script text, which gives an independent voice to tell a
# weak transcriber from a weak voice.
MACOS_VOICES = {"bs": "Lana", "es": "Paulina"}


async def speak_macos(http: aiohttp.ClientSession, lang: str, text: str) -> bytes:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "line.wav"
        process = await asyncio.create_subprocess_exec(
            "say", "-v", MACOS_VOICES[lang], "-o", str(path),
            "--file-format=WAVE", "--data-format=LEI16@16000", text,
        )  # fmt: skip
        await process.wait()
        return path.read_bytes()


async def speak_openai(http: aiohttp.ClientSession, lang: str, text: str) -> bytes:
    key = get_settings().openai_api_key.get_secret_value()
    body = {
        "model": "gpt-4o-mini-tts",
        "voice": "coral",
        "input": text,
        "response_format": "wav",
        "instructions": f"Speak {LANGUAGES[lang].english_name}, in a calm, clear voice, "
        "like a receptionist at a clinic on the phone.",
    }
    async with http.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {key}"},
        json=body,
    ) as r:
        r.raise_for_status()
        return await r.read()


async def hear_deepgram(
    http: aiohttp.ClientSession, lang: str, audio: bytes, numbers: bool = False
) -> str:
    """Plain sentences are scored word for word, so formatting is off. Sentences with numbers are
    scored on their digits, with formatting on, which is how the product runs it."""
    key = get_settings().deepgram_api_key.get_secret_value()
    formatting = "true" if numbers else "false"
    url = (
        "https://api.deepgram.com/v1/listen?model=nova-3"
        f"&language={LANGUAGES[lang].locale}&smart_format={formatting}&punctuate={formatting}"
    )
    headers = {"Authorization": f"Token {key}", "Content-Type": "audio/wav"}
    async with http.post(url, headers=headers, data=audio) as r:
        r.raise_for_status()
        reply = await r.json()
    return reply["results"]["channels"][0]["alternatives"][0]["transcript"]


async def hear_openai(
    http: aiohttp.ClientSession, lang: str, audio: bytes, numbers: bool = False
) -> str:
    key = get_settings().openai_api_key.get_secret_value()
    form = aiohttp.FormData()
    form.add_field("file", audio, filename="line.wav", content_type="audio/wav")
    form.add_field("model", "gpt-4o-transcribe")
    form.add_field("language", lang)
    async with http.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        data=form,
    ) as r:
        r.raise_for_status()
        return (await r.json())["text"]


VOICES = {"deepgram": speak_deepgram, "openai": speak_openai, "macos": speak_macos}
EARS = {"deepgram": hear_deepgram, "openai": hear_openai}


def has_voice(voice: str, lang: str) -> bool:
    if voice == "deepgram":
        return lang in DEEPGRAM_VOICES
    if voice == "macos":
        return lang in MACOS_VOICES and sys.platform == "darwin"
    return True


def score(text: str, heard: str, numeric: bool) -> dict:
    """A sentence with numbers is not scored (see languages.yaml); any other, on its words."""
    return {"numeric": True} if numeric else {"wer": word_error_rate(text, heard)}


async def one(http, gate, lang, voice, ear, index, text, numeric, audio_cache):
    """One sentence through one voice and one transcriber. Never raises: an error is a result."""
    async with gate:
        try:
            began = time.perf_counter()
            if (lang, voice, index) not in audio_cache:
                audio_cache[(lang, voice, index)] = (
                    await VOICES[voice](http, lang, text),
                    time.perf_counter() - began,
                )
            audio, spoke_in = audio_cache[(lang, voice, index)]
            SAMPLES.mkdir(parents=True, exist_ok=True)
            (SAMPLES / f"{lang}-{voice}-{index + 1}.wav").write_bytes(audio)
            began = time.perf_counter()
            heard = await EARS[ear](http, lang, audio, numeric)
            scored = score(text, heard, numeric)
            return {
                "language": lang, "voice": voice, "ear": ear, "sentence": index + 1,
                "heard": heard, "text": text, "speak_seconds": spoke_in,
                "hear_seconds": time.perf_counter() - began, **scored,
            }  # fmt: skip
        except Exception as problem:
            return {
                "language": lang, "voice": voice, "ear": ear, "sentence": index + 1,
                "error": f"{type(problem).__name__}: {str(problem)[:120]}", "text": text,
            }  # fmt: skip


def table(results: list[dict]) -> str:
    lines = [
        "| Language | Voice | Transcriber | Mean WER | Worst | Speak (s) | Hear (s) | Sentences |",
        "|---|---|---|---|---|---|---|---|",
    ]
    keys = sorted({(r["language"], r["voice"], r["ear"]) for r in results})
    for lang, voice, ear in keys:
        mine = [r for r in results if (r["language"], r["voice"], r["ear"]) == (lang, voice, ear)]
        done = [r for r in mine if "error" not in r]
        plain = [r["wer"] for r in done if "wer" in r]
        if not plain:
            why = mine[0].get("error", "?")[:50]
            lines.append(f"| {lang} | {voice} | {ear} | failed ({why}) | | | | 0 |")
            continue
        lines.append(
            f"| {lang} | {voice} | {ear} | {statistics.mean(plain):.2f} | {max(plain):.2f} "
            f"| {statistics.mean(r['speak_seconds'] for r in done):.1f} "
            f"| {statistics.mean(r['hear_seconds'] for r in done):.1f} "
            f"| {len(plain)} scored |"
        )
    lines += ["", 'Sentences with numbers, as heard (not scored: "nine" and 9 are both right):']
    for r in sorted(
        (r for r in results if r.get("numeric")),
        key=lambda r: (r["language"], r["voice"], r["ear"], r["sentence"]),
    ):
        lines.append(
            f"  {r['language']} {r['voice']}>{r['ear']} s{r['sentence']}: {r['heard'][:130]}"
        )
    return "\n".join(lines)


def rescore(path: Path) -> int:
    """Score a saved run again with the current scoring, without calling any service."""
    data = yaml.safe_load((HERE / "languages.yaml").read_text())
    results = json.loads(path.read_text())
    for r in results:
        if "heard" in r:
            for key in ("wer", "numeric"):
                r.pop(key, None)
            numeric = (r["sentence"] - 1) in data[r["language"]].get("numeric", [])
            r.update(score(r["text"], r["heard"], numeric))
    print(table(results))
    return 0


async def main(languages: list[str], voices: list[str], ears: list[str]) -> int:
    data = yaml.safe_load((HERE / "languages.yaml").read_text())
    gate, cache = asyncio.Semaphore(4), {}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as http:
        jobs = [
            one(http, gate, lang, voice, ear, i, text, i in data[lang].get("numeric", []), cache)
            for lang in languages
            for voice in voices
            if has_voice(voice, lang)
            for ear in ears
            for i, text in enumerate(data[lang]["sentences"])
        ]
        results = await asyncio.gather(*jobs)
    print(table(results))
    report = HERE / "reports" / f"languages-{datetime.now():%Y-%m-%dT%H%M%S}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nfull results: {report}\naudio to listen to: {SAMPLES}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default=",".join(LANGUAGES))
    parser.add_argument("--tts", default="deepgram,openai,macos")
    parser.add_argument("--stt", default="deepgram,openai")
    parser.add_argument("--rescore", type=Path, help="score a saved run again; calls nothing")
    args = parser.parse_args()
    if args.rescore:
        sys.exit(rescore(args.rescore))
    sys.exit(asyncio.run(main(args.only.split(","), args.tts.split(","), args.stt.split(","))))
