"""The flow's structure: which step can do what. No model is involved here."""

from datetime import datetime

import pytest

from clinic_voice_agent.clinic import demo_clinic
from clinic_voice_agent.flow import GREETING, CallState, HelpWithAppointment, IdentifyCaller

NOW = datetime(2026, 11, 16, 10, 0)


def names(agent) -> set[str]:
    """Each tool's name: a function tool carries it in `.info`, a built-in tool is its class."""
    return {
        getattr(getattr(tool, "info", None), "name", None) or type(tool).__name__
        for tool in agent.tools
    }


def state() -> CallState:
    return CallState(clinic=demo_clinic(NOW), now=NOW)


def test_before_the_caller_is_identified_no_tool_can_touch_an_appointment():
    tools = names(IdentifyCaller())
    assert tools == {"caller_gave_name", "take_message", "EndCallTool"}
    assert not tools & {"find_free_slots", "move_appointment", "cancel_appointment"}


def test_the_appointment_step_cannot_exist_without_an_identified_patient():
    with pytest.raises(ValueError, match="identified"):
        HelpWithAppointment(state())


def test_the_appointment_step_knows_only_this_patients_appointment():
    call = state()
    call.patient = call.clinic.find_patient("Alex Rivera")
    step = HelpWithAppointment(call)
    assert names(step) == {
        "find_free_slots",
        "move_appointment",
        "cancel_appointment",
        "confirm_appointment",
        "take_message",
        "EndCallTool",
    }
    text = str(step.instructions)
    assert "Alex Rivera" in text and "shoulder physiotherapy" in text
    assert "tomorrow at 3:30 PM" in text and "wait for a clear yes" in text


def test_the_identify_step_is_told_nothing_about_any_patient():
    text = str(IdentifyCaller().instructions)
    for private in ("Alex", "Rivera", "shoulder", "Okafor", "3:30"):
        assert private not in text


def test_the_greeting_says_who_answers_and_that_it_is_automated():
    assert "Quillbrook Physio" in GREETING and "Emily" in GREETING and "automated" in GREETING
    for private in ("Alex", "appointment", "Okafor"):
        assert private not in GREETING
