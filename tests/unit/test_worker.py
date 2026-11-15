from types import SimpleNamespace

from clinic_voice_agent.worker import CLOSE_REASONS, describe_error


class TTS:  # stands in for a service object; only its class name is used
    pass


def test_an_error_is_reduced_to_the_service_what_it_said_and_whether_it_can_continue():
    fatal = SimpleNamespace(source=TTS(), error=SimpleNamespace(error="quota", recoverable=False))
    assert describe_error(fatal) == {"service": "TTS", "error": "quota", "recoverable": False}


def test_an_error_that_does_not_say_is_treated_as_survivable():
    """Ending a call is the drastic choice; it needs the service to say it cannot go on."""
    assert describe_error(SimpleNamespace(source=TTS(), error="blip"))["recoverable"] is True


def test_long_provider_messages_are_cut_so_a_record_stays_readable():
    event = SimpleNamespace(source=TTS(), error=SimpleNamespace(error="x" * 5000, recoverable=True))
    assert len(describe_error(event)["error"]) == 300


def test_a_call_record_says_who_ended_the_call_in_plain_words():
    assert CLOSE_REASONS["user_initiated"] == "agent_ended_call"
    assert CLOSE_REASONS["participant_disconnected"] == "caller_hung_up"
    assert CLOSE_REASONS["error"] == "service_failed"
