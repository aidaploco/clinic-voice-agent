from datetime import date, datetime

import pytest

from clinic_voice_agent.clinic import Clinic, ClinicError, Patient, demo_clinic
from clinic_voice_agent.spoken import say_when

NOW = datetime(2026, 11, 16, 10, 0)  # a Monday


def test_the_demo_clinic_has_one_appointment_tomorrow_and_three_free_times():
    clinic = demo_clinic(NOW)
    (appointment,) = clinic.appointments.values()
    assert appointment.start == datetime(2026, 11, 17, 15, 30)
    assert [s.start for s in clinic.free_slots()] == [
        datetime(2026, 11, 18, 10, 30),
        datetime(2026, 11, 19, 16, 30),
        datetime(2026, 11, 20, 9, 0),
    ]


def test_the_clinic_is_closed_at_weekends():
    friday = datetime(2026, 11, 20, 10, 0)
    (appointment,) = demo_clinic(friday).appointments.values()
    assert appointment.start.strftime("%A") == "Monday"


@pytest.mark.parametrize(
    "spoken", ["Alex Rivera", "alex rivera", "  ALEX   RIVERA ", "Álex Rivera."]
)
def test_a_patient_is_found_by_their_name_as_spoken(spoken):
    assert demo_clinic(NOW).find_patient(spoken).id == "patient-alex"


@pytest.mark.parametrize("spoken", ["Alex", "Rivera", "Alexa Rivera", "Sam Rivera", ""])
def test_a_partial_or_different_name_matches_nobody(spoken):
    assert demo_clinic(NOW).find_patient(spoken) is None


def test_two_patients_with_the_same_name_are_never_guessed_between():
    clinic = Clinic(
        patients={
            "a": Patient("a", "Alex Rivera", date(1980, 1, 1)),
            "b": Patient("b", "Alex Rivera", date(1980, 1, 1)),
        }
    )
    assert clinic.find_patient("Alex Rivera") is None


def test_moving_takes_the_slot_and_frees_the_old_time():
    clinic = demo_clinic(NOW)
    slot = clinic.free_slots()[1]
    moved = clinic.move("appt-alex", slot.id)
    assert (moved.start, moved.practitioner) == (datetime(2026, 11, 19, 16, 30), "Dr. Okafor")
    assert moved.status == "confirmed"  # choosing a new time says they are coming
    assert slot.id not in clinic.slots
    assert datetime(2026, 11, 17, 15, 30) in [s.start for s in clinic.slots.values()]
    assert len(clinic.slots) == 3


def test_a_slot_cannot_be_taken_twice_or_invented():
    clinic = demo_clinic(NOW)
    slot = clinic.free_slots()[0]
    clinic.move("appt-alex", slot.id)
    with pytest.raises(ClinicError, match="not free"):
        clinic.move("appt-alex", slot.id)
    with pytest.raises(ClinicError, match="not free"):
        clinic.move("appt-alex", "slot-made-up")


def test_a_cancelled_appointment_cannot_be_changed_and_is_no_longer_upcoming():
    clinic = demo_clinic(NOW)
    clinic.cancel("appt-alex")
    assert clinic.upcoming_appointment("patient-alex") is None
    with pytest.raises(ClinicError):
        clinic.confirm("appt-alex")


def test_times_are_said_the_way_people_say_them():
    assert (
        say_when(datetime(2026, 11, 17, 15, 30), NOW) == "tomorrow at three thirty in the afternoon"
    )
    assert say_when(datetime(2026, 11, 19, 9, 0), NOW) == "Thursday at nine in the morning"
    assert (
        say_when(datetime(2026, 11, 16, 12, 5), NOW) == "today at twelve oh five in the afternoon"
    )
    assert (
        say_when(datetime(2026, 11, 23, 0, 15), NOW)
        == "Monday the 23rd at twelve fifteen in the morning"
    )
    assert say_when(datetime(2026, 12, 11, 14, 0), NOW) == "Friday the 11th at two in the afternoon"


def test_a_time_is_spoken_in_words_with_no_digit_and_colon():
    from clinic_voice_agent.spoken import say_clock

    cases = {
        (9, 0): "nine in the morning", (10, 30): "ten thirty in the morning",
        (12, 0): "noon", (0, 0): "midnight", (16, 30): "four thirty in the afternoon",
        (15, 45): "three forty five in the afternoon", (18, 15): "six fifteen in the evening",
        (13, 5): "one oh five in the afternoon", (21, 20): "nine twenty at night",
        (11, 59): "eleven fifty nine in the morning",
    }  # fmt: skip
    for (hour, minute), spoken in cases.items():
        assert say_clock(datetime(2026, 11, 17, hour, minute)) == spoken
    for hour in range(24):
        for minute in range(60):
            text = say_clock(datetime(2026, 11, 17, hour, minute))
            assert not any(ch.isdigit() for ch in text), text
