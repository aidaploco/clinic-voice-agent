"""The flow's structure: which step can do what. No model is involved here."""

from datetime import date, datetime

import pytest

from clinic_voice_agent.clinic import demo_clinic
from clinic_voice_agent.flow import GREETING, CallState, HelpWithAppointment, IdentifyCaller
from clinic_voice_agent.gateway import Gateway

NOW = datetime(2026, 11, 16, 10, 0)


def names(agent) -> set[str]:
    """Each tool's name: a function tool carries it in `.info`, a built-in tool is its class."""
    return {
        getattr(getattr(tool, "info", None), "name", None) or type(tool).__name__
        for tool in agent.tools
    }


async def nobody_is_asked(read_back: str, caller_words: str) -> bool:
    raise AssertionError("no change is committed in these tests")


def state() -> CallState:
    return CallState(gateway=Gateway(demo_clinic(NOW), NOW, nobody_is_asked), now=NOW)


def test_before_the_caller_is_identified_no_tool_can_touch_an_appointment():
    tools = names(IdentifyCaller())
    assert tools == {
        "caller_gave_name",
        "caller_gave_date_of_birth",
        "take_message",
        "switch_language",
        "EndCallTool",
    }
    assert not tools & {"find_free_slots", "propose_change", "commit_change"}


def test_the_appointment_step_cannot_exist_without_an_identified_patient():
    with pytest.raises(ValueError, match="identified"):
        HelpWithAppointment(state())


def test_the_appointment_step_knows_only_this_patients_appointment():
    call = state()
    call.gateway.verify_identity("Alex Rivera", date(1990, 3, 14))
    step = HelpWithAppointment(call)
    assert names(step) == {
        "find_free_slots",
        "propose_change",
        "commit_change",
        "take_message",
        "switch_language",
        "EndCallTool",
    }
    text = str(step.instructions)
    assert "Alex Rivera" in text and "shoulder physiotherapy" in text
    assert "tomorrow at three thirty in the afternoon" in text and "1990" not in text


def test_the_identify_step_is_told_nothing_about_any_patient():
    text = str(IdentifyCaller().instructions)
    for private in ("Alex", "Rivera", "shoulder", "Okafor", "3:30", "1990"):
        assert private not in text


def test_the_greeting_says_who_answers_and_that_it_is_automated():
    assert "Quillbrook Physio" in GREETING and "Emily" in GREETING and "automated" in GREETING
    for private in ("Alex", "appointment", "Okafor"):
        assert private not in GREETING


def test_the_offer_sentence_lists_the_times_and_names_practitioners_only_when_they_differ():
    from clinic_voice_agent.flow import offer_sentence
    from clinic_voice_agent.gateway import Offer

    same = [
        Offer("a", "Tuesday at 10:30 AM", "Dr. Okafor"),
        Offer("b", "Thursday at 9 AM", "Dr. Okafor"),
    ]
    assert (
        offer_sentence(same)
        == "I can offer you Tuesday at 10:30 AM, or Thursday at 9 AM. Which would you like?"
    )
    mixed = [*same[:1], Offer("c", "Friday at 9 AM", "Dr. Lindqvist")]
    assert offer_sentence(mixed) == (
        "I can offer you Tuesday at 10:30 AM with Dr. Okafor, "
        "or Friday at 9 AM with Dr. Lindqvist. Which would you like?"
    )
    assert offer_sentence(same[:1]) == "I can offer you Tuesday at 10:30 AM. Which would you like?"


# ----- languages -----------------------------------------------------------------------------


class FakeVoices:
    """Stands in for the speech services: records which languages were asked for."""

    def __init__(self):
        self.asked = []

    def agent_args(self, language):
        self.asked.append(language)
        return {}

    def menu_audio(self, language, text):
        return None


def tool_of(step, name):
    return next(t for t in step.tools if getattr(getattr(t, "info", None), "name", "") == name)


def ctx_of(call):
    from types import SimpleNamespace

    return SimpleNamespace(userdata=call)


async def test_switching_language_hands_the_call_to_a_step_in_that_language_and_keeps_the_name():
    call = state()
    call.voices = FakeVoices()
    step = IdentifyCaller(state=call)
    step._name = "Alex Rivera"
    new = await tool_of(step, "switch_language")(ctx_of(call), language="es")
    assert isinstance(new, IdentifyCaller)
    assert new._language == "es" and new._switched and new._name == "Alex Rivera"
    assert call.gateway.language == "es"  # what the gateway words for the caller follows
    assert call.voices.asked == ["es"]  # the new step gets Spanish speech services


async def test_asking_for_the_language_already_in_use_changes_nothing():
    call = state()
    call.gateway.language = "nl"
    step = IdentifyCaller("inbound", "nl", state=call)
    answer = await tool_of(step, "switch_language")(ctx_of(call), language="nl")
    assert isinstance(answer, str) and "Already" in answer


async def test_the_appointment_step_can_switch_too_and_speaks_the_times_in_the_new_language():
    call = state()
    call.voices = FakeVoices()
    call.gateway.verify_identity("Alex Rivera", date(1990, 3, 14))
    step = HelpWithAppointment(call)
    new = await tool_of(step, "switch_language")(ctx_of(call), language="nl")
    assert isinstance(new, HelpWithAppointment) and new._language == "nl" and new._switched
    text = str(new.instructions)
    assert "morgen om half vier 's middags" in text  # the appointment, in Dutch
    assert "The call is in Dutch" in text and "tomorrow at" not in text


def test_english_prompts_carry_no_language_note_and_the_others_name_their_language():
    assert "The call is in" not in str(IdentifyCaller().instructions)
    for code, name in (("es", "Mexican Spanish"), ("nl", "Dutch"), ("bs", "Bosnian")):
        assert f"The call is in {name}" in str(IdentifyCaller("inbound", code).instructions)
    assert "call `switch_language`" in str(IdentifyCaller().instructions)


def test_a_step_without_voices_asks_for_none_and_a_switched_one_asks_for_its_languages():
    call = state()  # no voices: the text tests and the evals
    assert IdentifyCaller("inbound", "es", switched=True, state=call)._language == "es"
    call.voices = FakeVoices()
    IdentifyCaller("inbound", "bs", switched=True, state=call)
    IdentifyCaller(state=call)  # the first step uses the session's own speech services
    assert call.voices.asked == ["bs"]


def test_the_offer_sentence_is_worded_in_the_calls_language():
    from clinic_voice_agent.flow import offer_sentence
    from clinic_voice_agent.gateway import Offer

    offers = [Offer("a", "miércoles a las nueve de la mañana", "Dr. Okafor")]
    assert offer_sentence(offers, "es") == (
        "Le puedo ofrecer miércoles a las nueve de la mañana. ¿Cuál prefiere?"
    )


def test_the_opening_line_follows_the_direction_and_the_language():
    from clinic_voice_agent.flow import opening_line

    assert opening_line("inbound", "bs").startswith("Hvala što ste nazvali")
    assert opening_line("outbound", "nl").startswith("Hallo, u spreekt met Emily")
    assert opening_line("outbound", "xx") == opening_line("outbound", "en")
