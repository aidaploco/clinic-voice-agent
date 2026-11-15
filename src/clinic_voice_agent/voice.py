"""The three services of the voice: hearing, thinking and speaking.

Speaking has more than one provider on purpose. A text-to-speech account that
runs out of credit, or has an outage, returns no audio, and to a caller that is
an agent who has stopped talking mid-call. So the providers are tried in order
and the next one takes over when one fails.
"""

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


def build_stt(settings: Settings):
    return deepgram.STT(
        model=settings.stt_model,
        language="en-US",
        api_key=settings.deepgram_api_key.get_secret_value(),
    )


def build_llm(settings: Settings):
    return openai.LLM(model=settings.llm_model, api_key=settings.openai_api_key.get_secret_value())
