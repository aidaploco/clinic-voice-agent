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
