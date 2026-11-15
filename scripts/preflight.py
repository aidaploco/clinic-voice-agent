"""Check, before a call, that every service the receptionist needs will answer.

Each check makes one tiny real request. A provider that has run out of credit
answers here in plain words, instead of as silence in the middle of a call.

    uv run python scripts/preflight.py
"""

import asyncio
import sys

import aiohttp

from clinic_voice_agent import voice
from clinic_voice_agent.settings import get_settings


async def ask(http: aiohttp.ClientSession, method: str, url: str, **kwargs) -> str:
    """ "ok", or the reason the service gave for refusing."""
    try:
        async with http.request(method, url, **kwargs) as response:
            if response.status < 300:
                return "ok"
            body = (await response.text())[:200].replace("\n", " ")
            return f"HTTP {response.status}: {body}"
    except Exception as exc:  # noqa: BLE001 -- any failure is the answer here
        return f"{type(exc).__name__}: {exc}"


async def main() -> int:
    settings = get_settings()
    key = lambda secret: secret.get_secret_value() if secret else ""  # noqa: E731
    line = {"text": "Hi."}
    speech = {
        "deepgram": (
            "POST",
            f"https://api.deepgram.com/v1/speak?model={settings.deepgram_tts_model}",
            {"headers": {"Authorization": f"Token {key(settings.deepgram_api_key)}"}, "json": line},
        ),
        "openai": (
            "POST",
            "https://api.openai.com/v1/audio/speech",
            {
                "headers": {"Authorization": f"Bearer {key(settings.openai_api_key)}"},
                "json": {
                    "model": "gpt-4o-mini-tts",
                    "voice": settings.openai_tts_voice,
                    "input": "Hi.",
                },
            },
        ),
        "elevenlabs": (
            "POST",
            f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}",
            {
                "headers": {"xi-api-key": key(settings.elevenlabs_api_key)},
                "json": {**line, "model_id": "eleven_turbo_v2_5"},
            },
        ),
    }
    results: list[tuple[str, str]] = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as http:
        results.append((
            "hearing (Deepgram)",
            await ask(http, "GET", "https://api.deepgram.com/v1/projects",
                      headers={"Authorization": f"Token {key(settings.deepgram_api_key)}"}),
        ))  # fmt: skip
        results.append((
            f"thinking (OpenAI {settings.llm_model})",
            await ask(http, "POST", "https://api.openai.com/v1/chat/completions",
                      headers={"Authorization": f"Bearer {key(settings.openai_api_key)}"},
                      json={"model": settings.llm_model, "max_tokens": 1,
                            "messages": [{"role": "user", "content": "hi"}]}),
        ))  # fmt: skip
        try:
            names = voice.speech_provider_names(settings)
        except voice.NoVoiceError as exc:
            names, problem = [], str(exc)
            results.append(("speaking", problem))
        speaking = []
        for position, name in enumerate(names, start=1):
            method, url, kwargs = speech[name]
            answer = await ask(http, method, url, **kwargs)
            speaking.append(answer == "ok")
            results.append((f"speaking, choice {position} ({name})", answer))

    for what, answer in results:
        print(
            f"{'OK  ' if answer == 'ok' else 'FAIL'} {what}"
            + ("" if answer == "ok" else f"\n       {answer}")
        )
    required_ok = all(answer == "ok" for _, answer in results[:2]) and any(speaking)
    if required_ok and not all(speaking):
        print("\nShe can still speak: a later choice will take over from the failing one.")
    if not required_ok:
        print("\nNot ready: she needs hearing, thinking and at least one way of speaking.")
    return 0 if required_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
