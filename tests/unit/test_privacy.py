import json
from datetime import datetime

from clinic_voice_agent.clinic import demo_clinic
from clinic_voice_agent.gateway import Gateway
from clinic_voice_agent.privacy import call_id_for
from clinic_voice_agent.records import call_record, save

PHONE_ROOM = "inbound-_+14155550123_8AjnKGVfas8H"
NOW = datetime(2026, 11, 16, 10, 0)


async def yes(read_back, caller_words):
    return True


def test_a_phone_calls_room_name_becomes_an_id_with_no_number_in_it():
    call_id = call_id_for(PHONE_ROOM)
    assert call_id.startswith("phone-") and "4155550123" not in call_id and "+" not in call_id
    assert call_id == call_id_for(PHONE_ROOM)  # the same call always gets the same id
    assert call_id != call_id_for(PHONE_ROOM.replace("8Aj", "9Aj"))


def test_a_browser_calls_room_name_is_kept_even_if_it_is_all_digits():
    assert call_id_for("web-0a1b2c3d") == "web-0a1b2c3d"
    assert call_id_for("web-12345678") == "web-12345678"  # digits are not a number without a +


def test_a_stored_record_and_its_file_name_never_hold_the_callers_number(tmp_path):
    clinic = demo_clinic(NOW)
    record = call_record(call_id_for(PHONE_ROOM), NOW, Gateway(clinic, NOW, yes), clinic, [])
    path = save(record, tmp_path)
    assert "4155550123" not in path.name and "4155550123" not in json.dumps(record)
