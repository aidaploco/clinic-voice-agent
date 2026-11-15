import pytest
from livekit.agents import tts

from clinic_voice_agent import voice
from clinic_voice_agent.settings import Settings


def settings(**overrides) -> Settings:
    values = {"deepgram_api_key": "d", "openai_api_key": "o", "elevenlabs_api_key": "e"}
    return Settings(_env_file=None, **{**values, **overrides})


def test_speaking_has_a_second_choice_by_default():
    """One provider running out of credit must not silence the agent mid-call."""
    assert voice.speech_provider_names(settings()) == ["deepgram", "openai"]
    assert isinstance(voice.build_tts(settings()), tts.FallbackAdapter)


def test_the_order_of_providers_is_the_order_configured():
    chosen = settings(tts_providers="elevenlabs, OpenAI ,deepgram")
    assert voice.speech_provider_names(chosen) == ["elevenlabs", "openai", "deepgram"]


def test_a_provider_without_a_key_is_skipped_not_tried():
    chosen = settings(tts_providers="elevenlabs,deepgram", elevenlabs_api_key=None)
    assert voice.speech_provider_names(chosen) == ["deepgram"]
    assert not isinstance(voice.build_tts(chosen), tts.FallbackAdapter)


def test_no_way_of_speaking_is_an_error_at_the_start_not_silence_later():
    mute = settings(tts_providers="elevenlabs", elevenlabs_api_key=None)
    with pytest.raises(voice.NoVoiceError, match="has an API key"):
        voice.build_tts(mute)


def test_a_misspelt_provider_is_named():
    with pytest.raises(voice.NoVoiceError, match="elevenlabz"):
        voice.speech_provider_names(settings(tts_providers="deepgram,elevenlabz"))


def test_a_failing_provider_is_not_retried_while_the_caller_waits():
    adapter = voice.build_tts(settings())
    assert adapter._max_retry_per_tts == 0


def test_she_does_not_wait_three_seconds_to_decide_the_caller_has_finished():
    endpointing = voice.TURN_HANDLING["endpointing"]
    assert endpointing["max_delay"] <= 1.5
    assert endpointing["min_delay"] <= endpointing["max_delay"]
