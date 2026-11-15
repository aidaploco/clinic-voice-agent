"""The gateway's rules, with no model anywhere: what a call can and cannot do."""

from datetime import date, datetime

import pytest

from clinic_voice_agent.clinic import Appointment, Patient, demo_clinic
from clinic_voice_agent.gateway import MAX_IDENTITY_ATTEMPTS, Gateway, Refused

NOW = datetime(2026, 11, 16, 10, 0)  # Monday; the appointment is Tuesday 3:30 PM
BORN = date(1990, 3, 14)


class Says:
    """A consent check with a fixed answer, which remembers what it was asked."""

    def __init__(self, agreed: bool) -> None:
        self.agreed = agreed
        self.asked: list[tuple[str, str]] = []

    async def __call__(self, read_back: str, caller_words: str) -> bool:
        self.asked.append((read_back, caller_words))
        return self.agreed


def gateway(agreed: bool = True) -> Gateway:
    return Gateway(demo_clinic(NOW), NOW, Says(agreed))


def verified(agreed: bool = True) -> Gateway:
    call = gateway(agreed)
    call.verify_identity("Alex Rivera", BORN)
    return call


def refusal(call: Gateway) -> str:
    return call.audit[-1].reason


# ----- identity ---------------------------------------------------------------


def test_the_right_name_and_date_of_birth_unlock_the_call():
    call = gateway()
    assert call.patient is None
    assert call.verify_identity("alex rivera", BORN).id == "patient-alex"
    assert call.patient.full_name == "Alex Rivera"


@pytest.mark.parametrize(
    ("name", "born"),
    [
        ("Alex Rivera", date(1990, 3, 15)),
        ("Jordan Blake", BORN),
        ("Jordan Blake", date(2001, 1, 1)),
    ],
)
def test_a_wrong_name_and_a_wrong_date_get_the_same_answer(name, born):
    """So the check cannot be used to find out who is a patient here."""
    call = gateway()
    with pytest.raises(Refused) as wrong:
        call.verify_identity(name, born)
    with pytest.raises(Refused) as reference:
        gateway().verify_identity("Nobody Atall", date(1950, 1, 1))
    assert str(wrong.value) == str(reference.value)
    assert call.patient is None


def test_after_three_wrong_attempts_even_the_right_answer_is_refused():
    call = gateway()
    for _ in range(MAX_IDENTITY_ATTEMPTS):
        with pytest.raises(Refused):
            call.verify_identity("Alex Rivera", date(1991, 1, 1))
    with pytest.raises(Refused, match="closed"):
        call.verify_identity("Alex Rivera", BORN)
    assert refusal(call) == "locked" and call.patient is None


@pytest.mark.parametrize(
    "attempt",
    [
        lambda call: call.appointment(),
        lambda call: call.offer_slots(),
        lambda call: call.propose("cancel", caller_turn=1),
    ],
)
def test_a_caller_who_has_not_passed_the_check_can_do_nothing(attempt):
    call = gateway()
    with pytest.raises(Refused):
        attempt(call)
    assert refusal(call) == "not_verified"


async def test_a_caller_who_has_not_passed_the_check_cannot_commit():
    call = gateway()
    with pytest.raises(Refused):
        await call.commit(caller_turn=5, caller_words="yes")
    assert refusal(call) == "not_verified"


def test_refusals_say_nothing_about_any_patient():
    call = gateway()
    with pytest.raises(Refused) as refused:
        call.verify_identity("Alex Rivera", date(1991, 1, 1))
    for private in ("Alex", "1990", "March", "shoulder", "Okafor"):
        assert private not in str(refused.value)


def test_the_date_of_birth_is_never_written_to_the_audit_log():
    call = gateway()
    with pytest.raises(Refused):
        call.verify_identity("Alex Rivera", date(1991, 1, 1))
    call.verify_identity("Alex Rivera", BORN)
    logged = str([event.as_dict() for event in call.audit])
    assert "1990" not in logged and "1991" not in logged


# ----- one patient ------------------------------------------------------------


def test_a_call_sees_only_its_own_patients_appointment():
    clinic = demo_clinic(NOW)
    clinic.patients["patient-sam"] = Patient("patient-sam", "Sam Ortega", date(1985, 7, 2))
    clinic.appointments["appt-sam"] = Appointment(
        "appt-sam", "patient-sam", datetime(2026, 11, 17, 9, 0), "Dr. Lindqvist", "knee review"
    )
    call = Gateway(clinic, NOW, Says(True))
    call.verify_identity("Alex Rivera", BORN)
    assert call.appointment().id == "appt-alex"
    with pytest.raises(Refused):
        call.verify_identity("Sam Ortega", date(1985, 7, 2))  # one patient per call
    assert call.patient.id == "patient-alex"


# ----- offered times ----------------------------------------------------------


def test_free_times_are_offered_under_ids_made_up_for_the_call():
    clinic = demo_clinic(NOW)
    call = Gateway(clinic, NOW, Says(True))
    call.verify_identity("Alex Rivera", BORN)
    offers = call.offer_slots()
    assert len(offers) == 3
    assert not {offer.id for offer in offers} & set(clinic.slots)
    assert [offer.id for offer in call.offer_slots()] == [offer.id for offer in offers]


def test_a_real_slot_id_that_was_not_offered_cannot_be_proposed():
    clinic = demo_clinic(NOW)
    call = Gateway(clinic, NOW, Says(True))
    call.verify_identity("Alex Rivera", BORN)
    real_slot = next(iter(clinic.slots))
    for made_up in (real_slot, "option-0000", "Saturday 8 PM", None):
        with pytest.raises(Refused):
            call.propose("move", caller_turn=1, offer_id=made_up)
        assert refusal(call) == "not_offered"


# ----- propose, then commit ---------------------------------------------------


async def test_a_change_is_proposed_read_back_and_committed_after_a_yes():
    call = verified()
    thursday = call.offer_slots()[1]
    proposal = call.propose("move", caller_turn=3, offer_id=thursday.id)
    assert "Thursday at 4:30 PM" in proposal.read_back
    assert call.appointment().start == datetime(2026, 11, 17, 15, 30)  # nothing yet

    moved = await call.commit(caller_turn=4, caller_words="Yes please.")
    assert moved.start == datetime(2026, 11, 19, 16, 30) and moved.status == "confirmed"

    last = call.audit[-1]
    assert (last.operation, last.outcome) == ("commit_change", "allowed")
    assert last.details["proposal"] == proposal.id
    assert last.details["confirmation"] == {"read_back": proposal.read_back, "said": "Yes please."}


async def test_a_commit_in_the_same_turn_as_the_proposal_is_refused():
    """The model cannot propose and commit in one breath: the caller must speak in between."""
    call = verified()
    call.propose("cancel", caller_turn=3)
    with pytest.raises(Refused):
        await call.commit(caller_turn=3, caller_words="Cancel it. Yes, I'm sure.")
    assert refusal(call) == "no_answer_yet"
    assert call.appointment().status == "scheduled"


async def test_a_commit_without_a_proposal_is_refused():
    call = verified()
    with pytest.raises(Refused):
        await call.commit(caller_turn=9, caller_words="yes")
    assert refusal(call) == "nothing_proposed"


async def test_an_answer_that_is_not_a_clear_yes_changes_nothing_and_cannot_be_reused():
    consent = Says(False)
    call = Gateway(demo_clinic(NOW), NOW, consent)
    call.verify_identity("Alex Rivera", BORN)
    proposal = call.propose("cancel", caller_turn=3)

    with pytest.raises(Refused):
        await call.commit(caller_turn=4, caller_words="Hmm, hold on.")
    assert refusal(call) == "not_a_clear_yes"
    assert consent.asked == [(proposal.read_back, "Hmm, hold on.")]

    consent.agreed = True  # even so: the same turn is not a new answer
    with pytest.raises(Refused):
        await call.commit(caller_turn=4, caller_words="Hmm, hold on.")
    assert refusal(call) == "no_answer_yet"

    await call.commit(caller_turn=5, caller_words="Yes, cancel it.")
    assert call.appointment() is None


async def test_a_committed_proposal_cannot_be_committed_twice():
    call = verified()
    call.propose("confirm", caller_turn=1)
    await call.commit(caller_turn=2, caller_words="Yes.")
    with pytest.raises(Refused):
        await call.commit(caller_turn=3, caller_words="Yes.")
    assert refusal(call) == "nothing_proposed"


async def test_a_time_taken_by_someone_else_before_the_yes_is_refused():
    clinic = demo_clinic(NOW)
    call = Gateway(clinic, NOW, Says(True))
    call.verify_identity("Alex Rivera", BORN)
    offer = call.offer_slots()[0]
    proposal = call.propose("move", caller_turn=1, offer_id=offer.id)
    clinic.slots.pop(proposal.slot_id)
    with pytest.raises(Refused):
        await call.commit(caller_turn=2, caller_words="Yes.")
    assert refusal(call) == "clinic_refused"
    assert call.appointment().start == datetime(2026, 11, 17, 15, 30)


# ----- messages and the log ---------------------------------------------------


def test_anyone_can_leave_a_message():
    clinic = demo_clinic(NOW)
    call = Gateway(clinic, NOW, Says(True))
    call.take_message("Jordan Blake", "Please call me back.")
    assert (
        clinic.messages[0].caller_name == "Jordan Blake" and clinic.messages[0].patient_id is None
    )


def test_every_request_is_logged_allowed_or_refused():
    call = gateway()
    with pytest.raises(Refused):
        call.offer_slots()
    call.verify_identity("Alex Rivera", BORN)
    call.offer_slots()
    assert [(e.operation, e.outcome) for e in call.audit] == [
        ("offer_slots", "refused"),
        ("identity_check", "allowed"),
        ("offer_slots", "allowed"),
    ]
