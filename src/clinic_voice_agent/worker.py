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
from livekit import rtc
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli
from livekit.plugins import silero

from clinic_voice_agent import limits, live, records, review, store, voice
from clinic_voice_agent.allowlist import admit, admit_dialled
from clinic_voice_agent.clinic import demo_clinic
from clinic_voice_agent.consent import ModelConsent
from clinic_voice_agent.flow import CallState
from clinic_voice_agent.gateway import Gateway
from clinic_voice_agent.hearing import DeafnessWatch
from clinic_voice_agent.latency import latency_of
from clinic_voice_agent.locales import locale_of
from clinic_voice_agent.menu import ChooseLanguage, watch_keypad
from clinic_voice_agent.outbound import direction_of
from clinic_voice_agent.privacy import call_id_for
from clinic_voice_agent.settings import get_settings
from clinic_voice_agent.timeline import Timeline

# LiveKit's own connection settings (LIVEKIT_URL, LIVEKIT_API_KEY,
# LIVEKIT_API_SECRET) are read from the environment by the framework.
load_dotenv()

logger = logging.getLogger("clinic_voice_agent.worker")

WORKER_NAME = get_settings().agent_name

# How long after speech ends the transcript may take before the framework reports a miss.
TRANSCRIPTION_TIMEOUT = 4.0

# How long to wait for someone to be in the room before giving up on the call.
JOIN_SECONDS = 30

# How long the post-call review may take before the record is written without it.
REVIEW_SECONDS = 20

# The framework's reasons for a session closing, in the words of a call record.
CLOSE_REASONS = {
    "user_initiated": "agent_ended_call",  # our own end-call tool closed it
    "participant_disconnected": "caller_hung_up",
    "error": "service_failed",
}


def concurrency_load(worker: AgentServer) -> float:
    """How full this worker is, by calls running; at the cap it is given no new calls."""
    return limits.concurrency_load(len(worker.active_jobs), get_settings().max_concurrent_calls)


server = AgentServer(load_fnc=concurrency_load)


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

    # Join the room first: who is calling is only known once they are in it. A phone caller is
    # checked against the allowlist before anything is spent on them (no speech, no model, no
    # record), and a call nobody joins is not waited for forever.
    await ctx.connect()
    try:
        caller = await asyncio.wait_for(ctx.wait_for_participant(), timeout=JOIN_SECONDS)
    except TimeoutError:
        logger.warning("nobody joined the room within %s seconds", JOIN_SECONDS)
        return
    direction = direction_of(ctx.job.metadata)
    is_phone = caller.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
    number = caller.attributes.get("sip.phoneNumber")
    if direction == "outbound":
        admission = admit_dialled(is_phone, caller.identity, number, settings.allowed_set)
    else:
        admission = admit(is_phone=is_phone, caller_number=number, allowed=settings.allowed_set)
    if not admission.allowed:
        logger.warning("turning away a call: %s (%s)", admission.reason, admission.caller)
        ctx.delete_room()
        return

    # What is stored and logged by this project names the call by an id, never by the room name,
    # which for a phone call holds the caller's number.
    call_id = call_id_for(ctx.room.name)
    ctx.log_context_fields = {**ctx.log_context_fields, "room": call_id}

    started = datetime.now()
    if limits.calls_today(settings.recordings_dir, started) >= settings.daily_call_cap:
        await turn_away(ctx, settings)
        return

    clinic = demo_clinic(started)
    llm = voice.build_llm(settings)
    gateway = Gateway(clinic, started, consent=ModelConsent(llm))
    gateway.on_event = live.event_publisher(
        lambda text, topic: ctx.room.local_participant.send_text(text, topic=topic)
    )
    timeline = Timeline()
    state = CallState(gateway=gateway, now=started, voices=voice.Voices(settings), phone=is_phone)
    watch_keypad(ctx.room, state, timeline)
    session = AgentSession[CallState](
        userdata=state,
        vad=ctx.proc.userdata["vad"],
        stt=voice.build_stt(settings),
        llm=llm,
        tts=voice.build_tts(settings),
        turn_handling=voice.TURN_HANDLING,
        user_away_timeout=settings.silence_seconds,  # both sides quiet this long: "away"
        transcription_timeout=TRANSCRIPTION_TIMEOUT,
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
        await session.say(locale_of(gateway.language).time_limit_goodbye)

    time_limit = asyncio.create_task(
        limits.hang_up_after(settings.max_call_seconds, say_time_limit_goodbye, ctx.delete_room)
    )

    ending_now = False
    hang_ups: set[asyncio.Task] = set()

    def end_call(why: str, goodbye: str) -> None:
        """Say goodbye and hang up, once, whatever raised it."""
        nonlocal ending_now
        if ending_now:
            return
        ending_now = True

        async def say_goodbye() -> None:
            ending.setdefault("why", why)
            await session.say(goodbye)

        task = asyncio.create_task(limits.hang_up_after(0, say_goodbye, ctx.delete_room))
        hang_ups.add(task)  # a task nobody holds can be collected before it finishes
        task.add_done_callback(hang_ups.discard)

    watch = DeafnessWatch()

    def on_user_state(event: Any) -> None:
        if event.new_state == "away":
            logger.info(
                "the line has been silent for %s seconds; ending the call", settings.silence_seconds
            )
            end_call("silence", locale_of(gateway.language).silence_goodbye)

    def on_words(event: Any) -> None:
        if event.is_final:
            timeline.add("words", text=event.transcript.strip())
        if event.is_final and event.transcript.strip():
            watch.words_heard()

    def on_state(kind: str):
        def handler(event: Any) -> None:
            timeline.add(kind, to=str(event.new_state))

        return handler

    session.on("user_state_changed", on_state("user_state"))
    session.on("agent_state_changed", on_state("agent_state"))

    def on_speech_without_words(event: Any) -> None:
        timeline.add("speech_without_words", seconds=round(event.speech_duration, 2))
        if state.choosing:
            # At the language menu nothing is expected to be understood yet: a word the
            # transcriber cannot make out is not a transcriber that has failed.
            return
        if watch.speech_without_words(event.speech_duration):
            logger.error("speech was detected but no words came back, twice; ending the call")
            errors.append(
                {"service": "STT", "error": "no transcript after speech", "recoverable": False}
            )
            end_call("stt_silent", locale_of(gateway.language).deaf_goodbye)

    def on_close(event: Any) -> None:
        time_limit.cancel()
        reason = str(getattr(event, "reason", "closed")).split(".")[-1].lower()
        ending.setdefault("why", CLOSE_REASONS.get(reason, reason))

    session.on("error", on_error)
    session.on("close", on_close)
    session.on("user_state_changed", on_user_state)
    session.on("user_input_transcribed", on_words)
    session.on("user_transcription_timeout", on_speech_without_words)

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
            call_id,
            started,
            gateway,
            clinic,
            transcript,
            latency_of(session.history),
            ending.get("why", "worker_shutdown"),
            errors,
            checks,
            direction="outbound" if direction == "outbound" else None,
            timeline=timeline.entries,
        )
        # The file first: it needs nothing but a disk, so a database that is
        # down cannot lose the record of a call.
        path = records.save(record, settings.recordings_dir)
        logger.info("call record written to %s", path)
        if settings.database_url is not None:
            try:
                stored_id = await store.save_call(settings.database_url.get_secret_value(), record)
                logger.info("call stored as %s", stored_id)
            except Exception:
                logger.exception("the call was not stored in the database; the file has it")

    ctx.add_shutdown_callback(write_record)

    await session.start(agent=ChooseLanguage(direction, state, timeline), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(server)
