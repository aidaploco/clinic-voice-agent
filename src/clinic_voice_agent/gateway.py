"""The gateway: the only way a call can reach the clinic's records.

The language model decides what to say and which tool to ask for. It does not
decide what is allowed. Every request passes through here, and these rules are
code, not instructions:

- Nothing about an appointment can be read or changed until the caller has
  passed the identity check (full name and date of birth). After three wrong
  attempts the check is closed for the rest of the call.
- A call that passed is limited to that one patient's appointment. No method
  takes a patient or an appointment as an argument, so there is no way to ask
  for someone else's.
- Free times are handed out under ids made up for this call. Only a time that
  was offered in this call can be booked.
- A change happens in two steps. It is proposed, which changes nothing and
  produces a sentence to read back. It is committed only if the caller has
  spoken since the read-back and a separate check judges their words a clear
  yes.
- Every request, allowed or refused, is written to the audit log. A committed
  change carries the words the caller confirmed it with.
"""

import secrets
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal, Protocol

from clinic_voice_agent.clinic import Appointment, Clinic, ClinicError, Patient, Slot
from clinic_voice_agent.spoken import say_when

ChangeKind = Literal["move", "cancel", "confirm"]

MAX_IDENTITY_ATTEMPTS = 3


class Refused(Exception):
    """The gateway said no. `reason` is a short code for the log; the message
    is what the model is told, and never contains anything about a patient."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class Consent(Protocol):
    """Did the caller clearly agree to what was read back to them?"""

    async def __call__(self, read_back: str, caller_words: str) -> bool: ...


@dataclass(frozen=True)
class Capability:
    """What this call may touch: one patient, and nothing else."""

    patient_id: str


@dataclass(frozen=True)
class Offer:
    """A free time as this call knows it. The id means nothing outside the call."""

    id: str
    when: str
    practitioner: str


@dataclass
class Proposal:
    id: str
    kind: ChangeKind
    read_back: str
    # How many times the caller had spoken when this was read back. A commit
    # needs a later turn: the caller's answer.
    caller_turn: int
    slot_id: str | None = None


@dataclass
class AuditEvent:
    at: datetime
    operation: str
    outcome: Literal["allowed", "refused"]
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "at": self.at.isoformat(timespec="seconds"),
            "operation": self.operation,
            "outcome": self.outcome,
            "reason": self.reason,
            "details": self.details,
        }


class Gateway:
    def __init__(self, clinic: Clinic, now: datetime, consent: Consent) -> None:
        self._clinic = clinic
        self._now = now
        self._consent = consent
        self._capability: Capability | None = None
        self._identity_attempts = 0
        self._offers: dict[str, Slot] = {}
        self._pending: Proposal | None = None
        self.audit: list[AuditEvent] = []

    # ----- identity -------------------------------------------------------

    @property
    def patient(self) -> Patient | None:
        """The patient this call is limited to, once the identity check has passed."""
        if self._capability is None:
            return None
        return self._clinic.patients[self._capability.patient_id]

    def verify_identity(self, full_name: str, date_of_birth: date) -> Patient:
        """Unlock this call for the patient with this name and date of birth.

        A wrong name and a wrong date get the same answer, so the check cannot
        be used to find out who is a patient here.
        """
        if self._capability is not None:
            raise self._refuse("identity_check", "already_verified", "The caller is verified.")
        if self._identity_attempts >= MAX_IDENTITY_ATTEMPTS:
            raise self._refuse(
                "identity_check",
                "locked",
                "The identity check is closed for this call. Do not ask again. Offer to take a "
                "message for the clinic team.",
            )
        self._identity_attempts += 1
        patient = self._clinic.find_patient(full_name)
        if patient is None or patient.date_of_birth != date_of_birth:
            left = MAX_IDENTITY_ATTEMPTS - self._identity_attempts
            raise self._refuse(
                "identity_check",
                "no_match",
                "Those details do not match a patient record. "
                + (
                    "Ask for the full name and date of birth once more."
                    if left
                    else "That was the last attempt. Offer to take a message for the clinic team."
                ),
                attempt=self._identity_attempts,
            )
        self._capability = Capability(patient.id)
        self._allow("identity_check", patient_id=patient.id, attempt=self._identity_attempts)
        return patient

    # ----- reading --------------------------------------------------------

    def appointment(self) -> Appointment | None:
        """The verified patient's upcoming appointment."""
        return self._clinic.upcoming_appointment(self._require("read_appointment").patient_id)

    def offer_slots(self) -> list[Offer]:
        """Free times, each under an id made up for this call."""
        self._require("offer_slots")
        known = {slot.id: offer_id for offer_id, slot in self._offers.items()}
        offers = []
        for slot in self._clinic.free_slots():
            offer_id = known.get(slot.id) or f"option-{secrets.token_hex(2)}"
            self._offers[offer_id] = slot
            offers.append(Offer(offer_id, say_when(slot.start, self._now), slot.practitioner))
        self._allow("offer_slots", offers=[offer.id for offer in offers])
        return offers

    # ----- changing -------------------------------------------------------

    def propose(self, kind: ChangeKind, caller_turn: int, offer_id: str | None = None) -> Proposal:
        """Prepare a change and the sentence to read back. Changes nothing."""
        self._require("propose_change")
        appointment = self._current_appointment("propose_change")
        was = f"{appointment.treatment} with {appointment.practitioner}"
        when = say_when(appointment.start, self._now)
        slot_id = None
        if kind == "move":
            slot = self._offers.get(offer_id or "")
            if slot is None or slot.id not in self._clinic.slots:
                raise self._refuse(
                    "propose_change",
                    "not_offered",
                    "That time was not offered in this call or is no longer free. Call "
                    "`find_free_slots` and offer only the times it returns.",
                    kind=kind,
                    offer=offer_id,
                )
            slot_id = slot.id
            read_back = (
                f"Move your {was} from {when} to {say_when(slot.start, self._now)} "
                f"with {slot.practitioner}"
            )
        elif kind == "cancel":
            read_back = f"Cancel your {was} {when}"
        elif kind == "confirm":
            read_back = f"Confirm that you are coming to your {was} {when}"
        else:
            raise self._refuse("propose_change", "unknown_change", "There is no such change.")
        self._pending = Proposal(
            f"proposal-{secrets.token_hex(3)}", kind, read_back, caller_turn, slot_id
        )
        self._allow("propose_change", proposal=self._pending.id, kind=kind, read_back=read_back)
        return self._pending

    async def commit(self, caller_turn: int, caller_words: str) -> Appointment:
        """Carry out the pending change, if the caller has clearly agreed to it."""
        self._require("commit_change")
        pending = self._pending
        if pending is None:
            raise self._refuse(
                "commit_change",
                "nothing_proposed",
                "Nothing is waiting to be confirmed. Call `propose_change` first.",
            )
        if caller_turn <= pending.caller_turn or not caller_words.strip():
            raise self._refuse(
                "commit_change",
                "no_answer_yet",
                "The caller has not answered yet. Read the change back to them, ask for a yes "
                "or no, and wait for their answer.",
                proposal=pending.id,
            )
        if not await self._consent(pending.read_back, caller_words):
            # The same answer cannot be offered twice: a fresh one is needed.
            pending.caller_turn = caller_turn
            raise self._refuse(
                "commit_change",
                "not_a_clear_yes",
                "The caller's answer was not a clear yes, so nothing was changed. If they want "
                "it, ask again plainly; otherwise leave the appointment as it is.",
                proposal=pending.id,
                said=caller_words,
            )
        appointment = self._current_appointment("commit_change")
        try:
            if pending.kind == "move":
                done = self._clinic.move(appointment.id, pending.slot_id or "")
            elif pending.kind == "cancel":
                done = self._clinic.cancel(appointment.id)
            else:
                done = self._clinic.confirm(appointment.id)
        except ClinicError as exc:
            self._pending = None
            raise self._refuse(
                "commit_change",
                "clinic_refused",
                f"The change did not go through: {exc}. Nothing was changed.",
                proposal=pending.id,
            ) from exc
        self._pending = None
        self._offers = {k: v for k, v in self._offers.items() if v.id in self._clinic.slots}
        self._allow(
            "commit_change",
            proposal=pending.id,
            kind=pending.kind,
            appointment_id=done.id,
            confirmation={"read_back": pending.read_back, "said": caller_words},
        )
        return done

    def take_message(self, caller_name: str, text: str) -> None:
        """Leave a message for the clinic team. Open to any caller."""
        patient = self.patient
        self._clinic.leave_message(
            patient.full_name if patient else caller_name, text, patient.id if patient else None
        )
        self._allow("take_message", verified=patient is not None)

    # ----- internals ------------------------------------------------------

    def _require(self, operation: str) -> Capability:
        if self._capability is None:
            raise self._refuse(
                operation, "not_verified", "The caller has not passed the identity check."
            )
        return self._capability

    def _current_appointment(self, operation: str) -> Appointment:
        appointment = self.appointment()
        if appointment is None:
            raise self._refuse(
                operation,
                "no_appointment",
                "This patient has no upcoming appointment. Offer to take a message.",
            )
        return appointment

    def _allow(self, operation: str, **details: Any) -> None:
        self.audit.append(AuditEvent(datetime.now(), operation, "allowed", details=details))

    def _refuse(self, operation: str, reason: str, message: str, **details: Any) -> Refused:
        self.audit.append(AuditEvent(datetime.now(), operation, "refused", reason, details))
        return Refused(reason, message)
