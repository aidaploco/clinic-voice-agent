"""Settings, read from the environment or a local `.env` file."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # The three services of the voice: hearing, thinking, speaking.
    deepgram_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    elevenlabs_api_key: SecretStr | None = None

    llm_model: str = "gpt-4.1-mini"
    stt_model: str = "nova-3"

    # Text-to-speech providers, tried in this order; the next takes over when
    # one fails. Any of: deepgram, openai, elevenlabs. A provider without a key
    # is skipped.
    tts_providers: str = "deepgram,openai"
    deepgram_tts_model: str = "aura-2-thalia-en"
    openai_tts_voice: str = "coral"
    elevenlabs_voice_id: str = "cgSgspJ2msm6clMCkdW9"

    # Where each call's record (transcript and what the tools did) is written.
    recordings_dir: Path = Path("recordings")

    # Postgres for call records. Optional: without it a call's record is the
    # JSON file only.
    database_url: SecretStr | None = None

    @field_validator(
        "deepgram_api_key", "openai_api_key", "elevenlabs_api_key", "database_url", mode="before"
    )
    @classmethod
    def _blank_means_unset(cls, value):
        # `KEY=` in a .env file is "not set", never "the empty key".
        return None if isinstance(value, str) and not value.strip() else value

    def missing_voice_keys(self) -> list[str]:
        """The keys hearing and thinking cannot do without. Speaking is checked separately."""
        keys = {"DEEPGRAM_API_KEY": self.deepgram_api_key, "OPENAI_API_KEY": self.openai_api_key}
        return [name for name, value in keys.items() if value is None]


@lru_cache
def get_settings() -> Settings:
    return Settings()
