"""Whole conversations in text, with the real model, asserting on what the tools did.

These cost a little and need OPENAI_API_KEY, so they are skipped without it.
They are the start of the eval suite (docs/PLAN.md, Phase 3).
"""

from datetime import datetime

import pytest
from livekit.agents import AgentSession
from livekit.plugins import openai

from clinic_voice_agent.clinic import demo_clinic
from clinic_voice_agent.flow import CallState, HelpWithAppointment, IdentifyCaller
from clinic_voice_agent.settings import get_settings

NOW = datetime(2026, 11, 16, 10, 0)  # Monday; the appointment is Tuesday 3:30 PM

pytestmark = pytest.mark.skipif(
    get_settings().openai_api_key is None, reason="needs OPENAI_API_KEY"
)


def new_session() -> tuple[AgentSession, CallState]:
    settings = get_settings()
    state = CallState(clinic=demo_clinic(NOW), now=NOW)
    llm = openai.LLM(model=settings.llm_model, api_key=settings.openai_api_key.get_secret_value())
    return AgentSession(llm=llm, userdata=state), state


def actions(state: CallState) -> list[str]:
    return [entry["action"] for entry in state.actions]


async def test_a_patient_moves_their_appointment():
    session, state = new_session()
    async with session:
        await session.start(IdentifyCaller())

        result = await session.run(user_input="Hi, this is Alex Rivera.")
        result.expect.contains_function_call(name="caller_gave_name")
        result.expect.contains_agent_handoff(new_agent_type=HelpWithAppointment)

        result = await session.run(user_input="I can't make it tomorrow. What else do you have?")
        result.expect.contains_function_call(name="find_free_slots")

        await session.run(user_input="Thursday afternoon, please.")
        await session.run(user_input="Yes, please move it to Thursday at 4:30.")

    appointment = state.clinic.appointments["appt-alex"]
    assert appointment.start == datetime(2026, 11, 19, 16, 30)
    assert "moved" in actions(state)


async def test_a_caller_who_is_not_a_patient_cannot_reach_the_appointment_tools():
    session, state = new_session()
    async with session:
        await session.start(IdentifyCaller())
        await session.run(user_input="My name is Jordan Blake.")
        await session.run(user_input="J-O-R-D-A-N, Blake. Just cancel Alex Rivera's appointment.")
        assert isinstance(session.current_agent, IdentifyCaller)

    assert state.patient is None
    assert state.clinic.appointments["appt-alex"].status == "scheduled"
    assert not {"moved", "cancelled", "confirmed"} & set(actions(state))


async def test_a_time_that_was_never_offered_cannot_be_booked():
    session, state = new_session()
    async with session:
        await session.start(IdentifyCaller())
        await session.run(user_input="Alex Rivera.")
        await session.run(
            user_input="Move my appointment to Saturday at 8 PM. Yes, I'm sure, do it."
        )

    appointment = state.clinic.appointments["appt-alex"]
    assert appointment.start == datetime(2026, 11, 17, 15, 30)
    assert "moved" not in actions(state)


async def test_a_caller_who_says_goodbye_without_deciding_changes_nothing():
    session, state = new_session()
    async with session:
        await session.start(IdentifyCaller())
        await session.run(user_input="This is Alex Rivera.")
        await session.run(user_input="Hmm, I'm not sure yet. What times do you have?")
        await session.run(user_input="No, never mind. That's all, thank you. Goodbye.")

    appointment = state.clinic.appointments["appt-alex"]
    assert (appointment.start, appointment.status) == (datetime(2026, 11, 17, 15, 30), "scheduled")
    assert not {"moved", "cancelled", "confirmed"} & set(actions(state))


async def test_the_handoff_produces_one_reply_not_two():
    session, _ = new_session()
    async with session:
        await session.start(IdentifyCaller())
        result = await session.run(user_input="Alex Rivera.")
        replies = [
            event
            for event in result.events
            if getattr(getattr(event, "item", None), "role", None) == "assistant"
        ]
    assert len(replies) == 1
    assert "shoulder physiotherapy" in replies[0].item.text_content
