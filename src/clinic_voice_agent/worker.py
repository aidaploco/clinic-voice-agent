"""The worker: the process LiveKit hands calls to.

It registers with LiveKit under a name. When a call is dispatched to that
name, `handle_call` runs for it: one call, one fresh mock clinic, one
conversation flow.

    uv run python -m clinic_voice_agent.worker console   # talk to it in this terminal
    uv run python -m clinic_voice_agent.worker dev       # take calls from your LiveKit project
"""

import logging
from datetime import datetime

from dotenv import load_dotenv
from livekit.agents import AgentServer, AgentSession, JobContext, JobProcess, cli
from livekit.plugins import deepgram, elevenlabs, openai, silero

from clinic_voice_agent import records
from clinic_voice_agent.clinic import demo_clinic
from clinic_voice_agent.flow import CallState, IdentifyCaller
from clinic_voice_agent.latency import LatencyLog
from clinic_voice_agent.settings import get_settings

# LiveKit's own connection settings (LIVEKIT_URL, LIVEKIT_API_KEY,
# LIVEKIT_API_SECRET) are read from the environment by the framework.
load_dotenv()

logger = logging.getLogger("clinic_voice_agent.worker")

WORKER_NAME = "clinic-receptionist"

server = AgentServer()


def load_models(proc: JobProcess) -> None:
    """Runs once per worker process, before any call: load what every call needs."""
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = load_models


@server.rtc_session(agent_name=WORKER_NAME)
async def handle_call(ctx: JobContext) -> None:
    settings = get_settings()
    if missing := settings.missing_voice_keys():
        raise RuntimeError(f"cannot take calls: {', '.join(missing)} not set (see .env.example)")

    started = datetime.now()
    state = CallState(clinic=demo_clinic(started), now=started)
    session = AgentSession[CallState](
        userdata=state,
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(
            model=settings.stt_model,
            language="en-US",
            api_key=settings.deepgram_api_key.get_secret_value(),
        ),
        llm=openai.LLM(
            model=settings.llm_model, api_key=settings.openai_api_key.get_secret_value()
        ),
        tts=elevenlabs.TTS(
            voice_id=settings.tts_voice_id,
            api_key=settings.elevenlabs_api_key.get_secret_value(),
        ),
    )

    latency = LatencyLog()
    session.on("metrics_collected", lambda event: latency.add(event.metrics))

    async def write_record() -> None:
        record = records.call_record(
            ctx.room.name, started, state, session.history, latency.summary()
        )
        path = records.save(record, settings.recordings_dir)
        logger.info("call record written to %s", path)

    ctx.add_shutdown_callback(write_record)

    await ctx.connect()
    await session.start(agent=IdentifyCaller(), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(server)
