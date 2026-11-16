from datetime import date, datetime

from clinic_voice_agent.clinic import demo_clinic
from clinic_voice_agent.gateway import Gateway
from clinic_voice_agent.records import call_record

NOW = datetime(2026, 11, 16, 10, 0)


async def yes(read_back: str, caller_words: str) -> bool:
    return True


def test_a_call_that_unlocked_nothing_records_no_patient_and_no_appointment():
    clinic = demo_clinic(NOW)
    record = call_record("room", NOW, Gateway(clinic, NOW, yes), clinic, [])
    assert record["patient_id"] is None and record["appointment_after"] is None


async def test_a_cancelled_appointment_is_recorded_as_cancelled_not_as_missing():
    clinic = demo_clinic(NOW)
    gateway = Gateway(clinic, NOW, yes)
    gateway.verify_identity("Alex Rivera", date(1990, 3, 14))
    gateway.propose("cancel", caller_turn=1)
    await gateway.commit(caller_turn=2, caller_words="Yes.")

    record = call_record("room", NOW, gateway, clinic, [{"speaker": "caller", "text": "Yes."}])
    assert record["appointment_after"]["status"] == "cancelled"
    assert [e["operation"] for e in record["audit"]] == [
        "identity_check",
        "propose_change",
        "commit_change",
    ]
    assert record["audit"][-1]["details"]["confirmation"]["said"] == "Yes."


def test_a_record_carries_a_utc_offset_and_its_file_name_does_not(tmp_path):
    from datetime import datetime

    from clinic_voice_agent.records import save

    clinic = demo_clinic(NOW)
    record = call_record("web-0a1b2c3d", NOW, Gateway(clinic, NOW, yes), clinic, [])
    assert datetime.fromisoformat(record["started"]).utcoffset() is not None
    assert datetime.fromisoformat(record["ended"]).utcoffset() is not None
    name = save(record, tmp_path).name
    assert name.endswith("-web-0a1b2c3d.json") and "+" not in name and ":" not in name
    assert len(name.split("-web-")[0]) == len("2026-11-16T100000")


def test_a_record_says_when_emily_placed_the_call_and_otherwise_nothing():
    clinic = demo_clinic(NOW)
    gateway = Gateway(clinic, NOW, yes)
    assert (
        call_record("phone-out-0a1b2c3d", NOW, gateway, clinic, [], direction="outbound")[
            "direction"
        ]
        == "outbound"
    )
    assert call_record("web-0a1b2c3d", NOW, gateway, clinic, [])["direction"] is None
