"""The clinic's records. A mock: every patient, appointment and slot is invented.

This stands in for a real booking system. The agent never touches it directly;
it goes through the tools in `clinic_voice_agent.flow`, which decide what a
caller is allowed to do.
"""

import secrets
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta


class ClinicError(Exception):
    """The records refused the request. The message is safe to act on."""


@dataclass
class Patient:
    id: str
    full_name: str

    @property
    def first_name(self) -> str:
        return self.full_name.split()[0]


@dataclass
class Slot:
    id: str
    start: datetime
    practitioner: str


@dataclass
class Appointment:
    id: str
    patient_id: str
    start: datetime
    practitioner: str
    treatment: str
    status: str = "scheduled"  # scheduled | confirmed | cancelled


@dataclass
class Message:
    caller_name: str
    text: str
    patient_id: str | None = None


def _plain(text: str) -> str:
    """Lower-case, without accents or extra spaces, so names compare as spoken."""
    stripped = unicodedata.normalize("NFKD", text)
    letters = "".join(ch for ch in stripped if not unicodedata.combining(ch))
    return " ".join(letters.casefold().replace(".", " ").replace(",", " ").split())


def _new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(3)}"


@dataclass
class Clinic:
    patients: dict[str, Patient] = field(default_factory=dict)
    appointments: dict[str, Appointment] = field(default_factory=dict)
    slots: dict[str, Slot] = field(default_factory=dict)
    messages: list[Message] = field(default_factory=list)

    def find_patient(self, spoken_name: str) -> Patient | None:
        """The patient with this full name, or None. Never a guess between two."""
        wanted = _plain(spoken_name)
        matches = [p for p in self.patients.values() if _plain(p.full_name) == wanted]
        return matches[0] if len(matches) == 1 else None

    def upcoming_appointment(self, patient_id: str) -> Appointment | None:
        mine = [
            a
            for a in self.appointments.values()
            if a.patient_id == patient_id and a.status != "cancelled"
        ]
        return min(mine, key=lambda a: a.start, default=None)

    def free_slots(self, limit: int = 3) -> list[Slot]:
        return sorted(self.slots.values(), key=lambda s: s.start)[:limit]

    def move(self, appointment_id: str, slot_id: str) -> Appointment:
        appointment = self._appointment(appointment_id)
        slot = self.slots.pop(slot_id, None)
        if slot is None:
            raise ClinicError("that time is not free")
        # The time being given up becomes free for someone else.
        released = Slot(_new_id("slot"), appointment.start, appointment.practitioner)
        self.slots[released.id] = released
        appointment.start, appointment.practitioner = slot.start, slot.practitioner
        # A patient who picks a new time has said they are coming to it.
        appointment.status = "confirmed"
        return appointment

    def cancel(self, appointment_id: str) -> Appointment:
        appointment = self._appointment(appointment_id)
        appointment.status = "cancelled"
        return appointment

    def confirm(self, appointment_id: str) -> Appointment:
        appointment = self._appointment(appointment_id)
        appointment.status = "confirmed"
        return appointment

    def leave_message(self, caller_name: str, text: str, patient_id: str | None = None) -> None:
        self.messages.append(Message(caller_name, text, patient_id))

    def _appointment(self, appointment_id: str) -> Appointment:
        appointment = self.appointments.get(appointment_id)
        if appointment is None or appointment.status == "cancelled":
            raise ClinicError("there is no such appointment")
        return appointment


def _working_day_after(day: datetime) -> datetime:
    following = (day + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    while following.weekday() >= 5:  # the clinic is closed at weekends
        following += timedelta(days=1)
    return following


def demo_clinic(now: datetime) -> Clinic:
    """A clinic with one patient, one appointment on the next working day, and three free slots."""
    patient = Patient("patient-alex", "Alex Rivera")
    day = _working_day_after(now)
    appointment = Appointment(
        "appt-alex",
        patient.id,
        day.replace(hour=15, minute=30),
        "Dr. Okafor",
        "shoulder physiotherapy",
    )
    clinic = Clinic(patients={patient.id: patient}, appointments={appointment.id: appointment})
    for hour, minute, practitioner in (
        (10, 30, "Dr. Okafor"),
        (16, 30, "Dr. Okafor"),
        (9, 0, "Dr. Lindqvist"),
    ):
        day = _working_day_after(day)
        slot = Slot(_new_id("slot"), day.replace(hour=hour, minute=minute), practitioner)
        clinic.slots[slot.id] = slot
    return clinic
