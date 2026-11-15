from clinic_voice_agent.receptionist import INSTRUCTIONS, Receptionist


def test_she_says_what_she_is_and_does_not_pretend_to_have_tools():
    assert "automated" in INSTRUCTIONS
    assert "Quillbrook Physio" in INSTRUCTIONS and "Emily" in INSTRUCTIONS
    assert "cannot do that yet" in INSTRUCTIONS
    assert "Never give medical advice" in INSTRUCTIONS


def test_the_agent_starts_with_no_tools():
    """Until the tool gateway exists, she must not be able to act at all."""
    assert Receptionist().tools == []
