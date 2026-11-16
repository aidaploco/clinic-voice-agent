import json

from clinic_voice_agent import tracing


def test_phone_numbers_and_emails_are_taken_out_of_what_is_left():
    assert tracing.scrub_value("call +44 7700 900123 or a@b.org now") == (
        "call [removed] or [removed] now"
    )
    assert tracing.scrub_value(("ok", "+15550100123")) == ("ok", "[removed]")
    assert tracing.scrub_value(42) == 42


def test_a_home_folder_path_loses_the_name_in_it():
    assert tracing.scrub_value('File "/Users/jo/code/x.py" and /home/ann/y') == (
        'File "/~/code/x.py" and /~/y'
    )


def test_attributes_named_for_a_phone_a_room_or_a_person_are_dropped():
    kept = tracing.scrub_attributes(
        {
            "sip.phoneNumber": "+15550100123",
            "lk.room_name": "inbound-_+15550100123_x",
            "lk.participant_identity": "phone-1",
            "gen_ai.request.model": "gpt-4.1-mini",
            "lk.turn_latency": 2.1,
            "lk.blocking.stack": "File /Users/jo/x.py",
        }
    )
    assert kept == {"gen_ai.request.model": "gpt-4.1-mini", "lk.turn_latency": 2.1}


def test_with_nowhere_to_send_them_nothing_is_traced(tmp_path):
    assert tracing.build_provider(None, None) is None
    assert tracing.build_provider(None, tmp_path / "t.jsonl") is not None


def test_a_span_leaves_the_file_exporter_scrubbed(tmp_path):
    path = tmp_path / "spans.jsonl"
    provider = tracing.build_provider(None, path)
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("turn") as span:
        span.set_attribute("note", "reach me on +15550100123")
        span.set_attribute("sip.phoneNumber", "+15550100123")
        span.set_attribute("lk.turn_latency", 1.5)
    provider.shutdown()
    written = json.loads(path.read_text().splitlines()[0])
    assert written["attributes"] == {"note": "reach me on [removed]", "lk.turn_latency": 1.5}
