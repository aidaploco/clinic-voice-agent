"""The worker: the process LiveKit hands calls to.

It registers with LiveKit under a name. When a call is dispatched to that
name, `handle_call` runs for it: one call, one fresh mock clinic, one
conversation flow.

    uv run python -m clinic_voice_agent.worker console   # talk to it in this terminal
    uv run python -m clinic_voice_agent.worker start     # take calls from your LiveKit project
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli
from livekit.plugins import silero

from clinic_voice_agent import limits, records, review, store, voice
from clinic_voice_agent.clinic import demo_clinic
from clinic_voice_agent.consent import ModelConsent
from clinic_voice_agent.flow import CallState, IdentifyCaller
from clinic_voice_agent.gateway import Gateway
from clinic_voice_agent.latency import latency_of
from clinic_voice_agent.settings import get_settings

# LiveKit's own connection settings (LIVEKIT_URL, LIVEKIT_API_KEY,
# LIVEKIT_API_SECRET) are read from the environment by the framework.
load_dotenv()

logger = logging.getLogger("clinic_voice_agent.worker")

WORKER_NAME = "clinic-receptionist"

# How long the post-call review may take before the record is written without it.
REVIEW_SECONDS = 20

# The framework's reasons for a session closing, in the words of a call record.
CLOSE_REASONS = {
    "user_initiated": "agent_ended_call",  # our own end-call tool closed it
    "participant_disconnected": "caller_hung_up",
    "error": "service_failed",
}

server = AgentServer()


def load_models(proc: JobProcess) -> None:
    """Runs once per worker process, before any call: load what every call needs."""
    proc.userdata["vad"] = silero.VAD.load()
    if url := get_settings().database_url:
        try:
            store.migrate(url.get_secret_value())
        except Exception:
            # Calls are still taken and still recorded to a file.
            logger.exception("the database is not reachable; call records go to files only")


server.setup_fnc = load_models


def describe_error(event: Any) -> dict[str, Any]:
    """An error event from the session, reduced to what a person debugging needs."""
    error = getattr(event, "error", None)
    return {
        "service": type(getattr(event, "source", None)).__name__,
        "error": str(getattr(error, "error", error))[:300],
        "recoverable": bool(getattr(error, "recoverable", True)),
    }


async def turn_away(ctx: JobContext, settings: Any) -> None:
    """The day's cap is reached: say so, hang up. No record is written, so a refusal is no call."""
    logger.warning("daily call cap of %s reached; turning the call away", settings.daily_call_cap)
    session = AgentSession(tts=voice.build_tts(settings))
    await ctx.connect()
    await session.start(
        agent=Agent(instructions="You only announce that calls are closed."), room=ctx.room
    )
    await session.say(limits.CAP_REACHED)
    ctx.delete_room()


@server.rtc_session(agent_name=WORKER_NAME)
async def handle_call(ctx: JobContext) -> None:
    settings = get_settings()
    if missing := settings.missing_voice_keys():
        raise RuntimeError(f"cannot take calls: {', '.join(missing)} not set (see .env.example)")

    started = datetime.now()
    if limits.calls_today(settings.recordings_dir, started) >= settings.daily_call_cap:
        await turn_away(ctx, settings)
        return

    clinic = demo_clinic(started)
    llm = voice.build_llm(settings)
    gateway = Gateway(clinic, started, consent=ModelConsent(llm))
    session = AgentSession[CallState](
        userdata=CallState(gateway=gateway, now=started),
        vad=ctx.proc.userdata["vad"],
        stt=voice.build_stt(settings),
        llm=llm,
        tts=voice.build_tts(settings),
        turn_handling=voice.TURN_HANDLING,
    )

    errors: list[dict[str, Any]] = []
    ending: dict[str, str] = {}

    def on_error(event: Any) -> None:
        problem = describe_error(event)
        errors.append(problem)
        if problem["recoverable"]:
            return
        # A service she cannot do without has failed for good. An agent that
        # cannot hear, think or speak must not sit on the line in silence:
        # end the call and say why in the record.
        logger.error("ending the call: %s failed: %s", problem["service"], problem["error"])
        ending.setdefault("why", f"service_failed:{problem['service']}")
        # Closing the room hangs up on the caller, which is the point: a phone
        # line must not stay open to an agent that cannot serve it.
        ctx.delete_room()
        ctx.shutdown(reason=ending["why"])

    async def say_time_limit_goodbye() -> None:
        ending.setdefault("why", "time_limit")
        await session.say(limits.TIME_LIMIT_GOODBYE)

    time_limit = asyncio.create_task(
        limits.hang_up_after(settings.max_call_seconds, say_time_limit_goodbye, ctx.delete_room)
    )

    def on_close(event: Any) -> None:
        time_limit.cancel()
        reason = str(getattr(event, "reason", "closed")).split(".")[-1].lower()
        ending.setdefault("why", CLOSE_REASONS.get(reason, reason))

    session.on("error", on_error)
    session.on("close", on_close)

    async def write_record() -> None:
        transcript = records.transcript_of(session.history)
        audit = [event.as_dict() for event in gateway.audit]
        try:
            async with asyncio.timeout(REVIEW_SECONDS):
                checks = await review.review_call(transcript, audit, llm)
        except TimeoutError:
            checks = await review.review_call(transcript, audit, None)
        for check in checks:
            if check["verdict"] == "fail":
                logger.warning("review failed: %s: %s", check["name"], check["detail"])
        record = records.call_record(
            ctx.room.name,
            started,
            gateway,
            clinic,
            transcript,
            latency_of(session.history),
            ending.get("why", "worker_shutdown"),
            errors,
            checks,
        )
        # The file first: it needs nothing but a disk, so a database that is
        # down cannot lose the record of a call.
        path = records.save(record, settings.recordings_dir)
        logger.info("call record written to %s", path)
        if settings.database_url is not None:
            try:
                call_id = await store.save_call(settings.database_url.get_secret_value(), record)
                logger.info("call stored as %s", call_id)
            except Exception:
                logger.exception("the call was not stored in the database; the file has it")

    ctx.add_shutdown_callback(write_record)

    await ctx.connect()
    await session.start(agent=IdentifyCaller(), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(server)
