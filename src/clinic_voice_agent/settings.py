"""Settings, read from the environment or a local `.env` file."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The project folder (the one holding pyproject.toml). Defaults are anchored here, not to the
# folder a command happens to be run from: started from `web/`, a relative "web/dist" is
# looked for in `web/web/dist`, and a worker and a server started in different folders would
# write and read call records in different places.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

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
    recordings_dir: Path = PROJECT_ROOT / "recordings"

    # The LiveKit project calls run in. The framework reads the same three from the environment.
    livekit_url: str | None = None
    livekit_api_key: SecretStr | None = None
    livekit_api_secret: SecretStr | None = None

    # Where the built browser page is (`npm run build` in web/ writes it).
    web_dist: Path = PROJECT_ROOT / "web" / "dist"
    web_port: int = 8765
    # 127.0.0.1 unless the server runs in a container, where it must listen on all of the
    # container's addresses and the host publishes the port on 127.0.0.1 only (compose.yaml).
    web_host: str = "127.0.0.1"

    # The name the worker registers under and the page dispatches to. Change it to run a second
    # deployment (a container, say) on the same LiveKit project without sharing calls.
    agent_name: str = "clinic-receptionist"

    # What a call may cost. A call is ended at the time limit; once the day's cap of calls
    # is reached, further callers are told so and hung up on.
    max_call_seconds: int = 300
    daily_call_cap: int = 25

    # Postgres for call records. Optional: without it a call's record is the
    # JSON file only.
    database_url: SecretStr | None = None

    @field_validator(
        "deepgram_api_key",
        "openai_api_key",
        "elevenlabs_api_key",
        "database_url",
        "livekit_url",
        "livekit_api_key",
        "livekit_api_secret",
        mode="before",
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
