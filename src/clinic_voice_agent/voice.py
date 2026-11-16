"""The three services of the voice: hearing, thinking and speaking.

Speaking has more than one provider on purpose. A text-to-speech account that
runs out of credit, or has an outage, returns no audio, and to a caller that is
an agent who has stopped talking mid-call. So the providers are tried in order
and the next one takes over when one fails.
"""

import asyncio
from collections.abc import AsyncIterable
from typing import Any

from livekit import rtc
from livekit.agents import stt as stt_module
from livekit.agents import tts
from livekit.plugins import deepgram, elevenlabs, openai

from clinic_voice_agent.settings import Settings

# How long she waits, at most, after the caller goes quiet before deciding they
# have finished. The turn detector uses the long wait whenever it thinks the
# caller may not be done, which is often true of short answers like a name or
# "yes". The framework's default ceiling is 3 seconds, long enough that callers
# start asking whether anyone is there.
TURN_HANDLING = {"endpointing": {"min_delay": 0.5, "max_delay": 1.2}}


class NoVoiceError(RuntimeError):
    """No text-to-speech provider is configured with a key."""


def _speech_providers(settings: Settings) -> dict[str, tuple[object, object]]:
    """Each provider: its key, and how to build it. Built lazily, only when chosen."""
    return {
        "deepgram": (
            settings.deepgram_api_key,
            lambda key: deepgram.TTS(model=settings.deepgram_tts_model, api_key=key),
        ),
        "openai": (
            settings.openai_api_key,
            lambda key: openai.TTS(
                model="gpt-4o-mini-tts", voice=settings.openai_tts_voice, api_key=key
            ),
        ),
        "elevenlabs": (
            settings.elevenlabs_api_key,
            lambda key: elevenlabs.TTS(voice_id=settings.elevenlabs_voice_id, api_key=key),
        ),
    }


def speech_provider_names(settings: Settings) -> list[str]:
    """The configured providers that have a key, in the order they will be tried."""
    known = _speech_providers(settings)
    wanted = [name.strip().lower() for name in settings.tts_providers.split(",") if name.strip()]
    unknown = [name for name in wanted if name not in known]
    if unknown:
        raise NoVoiceError(f"unknown text-to-speech provider(s): {', '.join(unknown)}")
    return [name for name in wanted if known[name][0] is not None]


def build_tts(settings: Settings) -> tts.TTS:
    known = _speech_providers(settings)
    names = speech_provider_names(settings)
    if not names:
        raise NoVoiceError(
            f"none of the text-to-speech providers in TTS_PROVIDERS ({settings.tts_providers}) "
            "has an API key set"
        )
    voices = [known[name][1](known[name][0].get_secret_value()) for name in names]
    if len(voices) == 1:
        return voices[0]
    # No retries on a failing provider: the caller is waiting, so move on at once.
    return tts.FallbackAdapter(voices, max_retry_per_tts=0)


def build_stt(settings: Settings, language: str = "multi"):
    """The transcriber the session starts with. The first step listens in Deepgram's multilingual
    mode, because its callers answer a menu of four languages: with English alone, a Spanish or
    Dutch sentence comes back as nonsense and a Bosnian one as nothing (measured, ADR-0011)."""
    return deepgram.STT(
        model=settings.stt_model,
        language=language,
        api_key=settings.deepgram_api_key.get_secret_value(),
    )


def build_llm(settings: Settings):
    return openai.LLM(model=settings.llm_model, api_key=settings.openai_api_key.get_secret_value())


# The Deepgram voice for each language that has one, and how to word the instruction OpenAI's
# voice is given. Bosnian has no Deepgram voice, so OpenAI's speaks it.
DEEPGRAM_VOICES = {"es": "aura-2-estrella-es", "nl": "aura-2-beatrix-nl"}
DEEPGRAM_LISTEN = {"en": "en-US", "es": "es-MX", "nl": "nl-NL"}
MENU_HINT = "The caller chooses a language: English, español, Nederlands or bosanski."
BOSNIAN_HINT = "Razgovor na bosanskom jeziku. Pišite latinicom."  # left alone it writes Cyrillic


class Voices:
    """The speech services of each language, built when a language is first needed.

    Satisfies `flow.Voices`. English keeps what the session already has, apart from listening in
    English alone once the language is known; Spanish and Dutch use Deepgram to hear and speak
    (with OpenAI as the backup voice); Bosnian uses OpenAI to hear, with a hint to write in
    Latin script, and to speak (ADR-0010).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._ears: dict[str, stt_module.STT] = {}
        self._mouths: dict[str, tts.TTS | None] = {}
        self._clips: dict[tuple[str, str], list[rtc.AudioFrame]] = {}

    def _ear(self, language: str) -> stt_module.STT:
        if language not in self._ears:
            if language == "menu":
                # Four languages in one word each, on a phone line: measured, this one hears them
                # best when told which names to expect (scripts/choice_probe.py, ADR-0011).
                self._ears[language] = openai.STT(
                    model="gpt-4o-transcribe",
                    detect_language=True,
                    prompt=MENU_HINT,
                    api_key=self._settings.openai_api_key.get_secret_value(),
                )
            elif language == "bs":
                self._ears[language] = openai.STT(
                    model="gpt-4o-transcribe",
                    language="bs",
                    prompt=BOSNIAN_HINT,
                    api_key=self._settings.openai_api_key.get_secret_value(),
                )
            else:
                self._ears[language] = build_stt(self._settings, DEEPGRAM_LISTEN[language])
        return self._ears[language]

    def _mouth(self, language: str) -> tts.TTS | None:
        """The voice for a language, or None to keep the session's own (English)."""
        if language not in self._mouths:
            key = self._settings.openai_api_key.get_secret_value()
            style = f"Speak {language_name(language)}, calmly and clearly, like a receptionist."
            backup = openai.TTS(
                model="gpt-4o-mini-tts",
                voice=self._settings.openai_tts_voice,
                instructions=style,
                api_key=key,
            )
            if language in ("en", "menu"):
                self._mouths[language] = None
            elif language in DEEPGRAM_VOICES:
                first = deepgram.TTS(
                    model=DEEPGRAM_VOICES[language],
                    api_key=self._settings.deepgram_api_key.get_secret_value(),
                )
                self._mouths[language] = tts.FallbackAdapter([first, backup], max_retry_per_tts=0)
            else:
                self._mouths[language] = backup
        return self._mouths[language]

    def agent_args(self, language: str) -> dict[str, Any]:
        args: dict[str, Any] = {"stt": self._ear(language)}
        if (mouth := self._mouth(language)) is not None:
            args["tts"] = mouth
        return args

    async def _synthesize(self, language: str, text: str) -> list[rtc.AudioFrame]:
        mouth = self._mouth(language) or build_tts(self._settings)
        return [chunk.frame async for chunk in mouth.synthesize(text)]

    async def warm_menu(self, lines: list[tuple[str, str]]) -> None:
        """Make the audio of the menu lines, all at once, so no line waits for the one before."""
        todo = [(language, text) for language, text in lines if (language, text) not in self._clips]
        made = await asyncio.gather(*(self._synthesize(language, text) for language, text in todo))
        self._clips.update(zip(todo, made, strict=True))

    def menu_audio(self, language: str, text: str) -> AsyncIterable[rtc.AudioFrame]:
        """The audio of a menu line, from `warm_menu` (made now if it was not)."""

        async def frames() -> AsyncIterable[rtc.AudioFrame]:
            if (language, text) not in self._clips:
                await self.warm_menu([(language, text)])
            for frame in self._clips[(language, text)]:
                yield frame

        return frames()


def language_name(code: str) -> str:
    from clinic_voice_agent.locales import locale_of

    return locale_of(code).llm_language
