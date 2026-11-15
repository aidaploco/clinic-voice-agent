"""The conversation, as steps. Each step is an agent with only its own tools.

    IdentifyCaller  ->  HelpWithAppointment  ->  (end of call)

The model chooses the words. It does not choose which step it is in: the
tools for changing an appointment do not exist until the caller has been
matched to a patient, because the agent that owns them has not been created.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from livekit.agents import Agent, RunContext, ToolError, function_tool
from livekit.agents.beta.tools import EndCallTool

from clinic_voice_agent.clinic import Appointment, Clinic, ClinicError, Patient
from clinic_voice_agent.spoken import say_when

CLINIC_NAME = "Quillbrook Physio"
AGENT_NAME = "Emily"

GREETING = (
    f"Thank you for calling {CLINIC_NAME}. This is {AGENT_NAME}, the clinic's automated "
    "receptionist. May I have your full name, please?"
)

STYLE = f"""\
You are {AGENT_NAME}, the automated phone receptionist at {CLINIC_NAME}, a physiotherapy \
clinic. You are on a phone call.

How you speak:
- One or two short sentences at a time. No lists, no markdown, no emoji.
- Say times the way people say them, like "Thursday at 4:30 PM".
- Ask one question at a time and let the caller answer.
- If what you heard is cut off or makes no sense, say you did not catch it and ask again. \
Never guess.
- Never give medical advice. Offer to pass a message to the clinic team instead.
"""


@dataclass
class CallState:
    """What this one call knows. Shared by every step of the flow."""

    clinic: Clinic
    now: datetime
    patient: Patient | None = None
    # Slots this call was told about. Only these can be booked in this call.
    offered_slot_ids: set[str] = field(default_factory=set)
    # What the tools did, in order, for the call's record.
    actions: list[dict[str, Any]] = field(default_factory=list)

    def record(self, action: str, **details: Any) -> None:
        self.actions.append({"action": action, **details})


def _end_call() -> EndCallTool:
    return EndCallTool(end_instructions="Say a short goodbye.")


class IdentifyCaller(Agent):
    """Step one: find out who is calling. Nothing about any appointment is known here."""

    def __init__(self) -> None:
        super().__init__(
            instructions=STYLE
            + """
Right now you do not know who is calling, and you know nothing about any appointment.
- Get the caller's full name, then call `caller_gave_name`.
- If the name is not recognised, ask them to repeat it once. If it still is not recognised, \
offer to take a message with `take_message`, then end the call.
- Do not discuss appointments, times or practitioners in this step.
""",
            tools=[_end_call()],
        )

    async def on_enter(self) -> None:
        # A fixed greeting, not a generated one: the first thing a caller hears
        # should be the same every time, and it should be fast.
        self.session.say(GREETING)

    @function_tool
    async def caller_gave_name(self, ctx: RunContext[CallState], full_name: str):
        """Call this as soon as the caller has told you their full name.

        Args:
            full_name: The caller's first and last name, as they said it.
        """
        state = ctx.userdata
        patient = state.clinic.find_patient(full_name)
        if patient is None:
            state.record("name_not_recognised", name=full_name)
            raise ToolError(
                "No patient is registered under that name. Ask them to repeat or spell it once; "
                "if it still does not match, offer to take a message."
            )
        state.patient = patient
        state.record("identified", patient_id=patient.id)
        # Returning the next step hands the call over to it. Nothing is said
        # here: the new step opens by itself, so the caller hears one reply.
        return HelpWithAppointment(state)

    @function_tool
    async def take_message(self, ctx: RunContext[CallState], caller_name: str, message: str) -> str:
        """Leave a message for the clinic team from a caller who could not be identified.

        Args:
            caller_name: The name the caller gave.
            message: What they want the clinic to know or do, in their words.
        """
        ctx.userdata.clinic.leave_message(caller_name, message)
        ctx.userdata.record("message_taken", caller_name=caller_name)
        return "The message has been passed to the clinic team."


class HelpWithAppointment(Agent):
    """Step two: the caller is a known patient. Their appointment can be changed."""

    def __init__(self, state: CallState) -> None:
        if state.patient is None:
            raise ValueError("this step exists only after the caller has been identified")
        self._patient = state.patient
        appointment = state.clinic.upcoming_appointment(state.patient.id)
        if appointment is None:
            about = "They have no upcoming appointment. You can only take a message."
        else:
            about = (
                f"Their upcoming appointment: {appointment.treatment} with "
                f"{appointment.practitioner}, {say_when(appointment.start, state.now)}."
            )
        super().__init__(
            instructions=STYLE
            + f"""
You are speaking with {state.patient.full_name}, a registered patient. {about}

What you can do, with your tools:
- Confirm the appointment, cancel it, or move it to a free time.
- To move it, call `find_free_slots` and offer the times it returns, all in one sentence. \
Offer no other times. If they want a time that is not in that list, say you do not have it.
- Before you change anything, say what you are about to do and wait for a clear yes.
- Change nothing the caller did not ask for. If they decline, hesitate, or say goodbye \
without deciding, leave the appointment exactly as it is and say so.
- For anything else, take a message with `take_message`.
- When the caller has what they need, say what was done in one sentence and end the call.
""",
            tools=[_end_call()],
        )

    async def on_enter(self) -> None:
        self.session.generate_reply(
            instructions=(
                f"Greet {self._patient.first_name} by first name, say which appointment you "
                "can see for them (treatment, practitioner, when), and ask how you can help."
            )
        )

    def _appointment(self, state: CallState) -> Appointment:
        appointment = state.clinic.upcoming_appointment(self._patient.id)
        if appointment is None:
            raise ToolError("This patient has no upcoming appointment. Offer to take a message.")
        return appointment

    @function_tool
    async def find_free_slots(self, ctx: RunContext[CallState]) -> list[dict[str, str]]:
        """Look up the free times the appointment could be moved to."""
        state = ctx.userdata
        slots = state.clinic.free_slots()
        state.offered_slot_ids.update(slot.id for slot in slots)
        state.record("slots_offered", slot_ids=[slot.id for slot in slots])
        if not slots:
            raise ToolError("There are no free times. Offer to take a message for the clinic team.")
        return [
            {
                "slot_id": slot.id,
                "when": say_when(slot.start, state.now),
                "practitioner": slot.practitioner,
            }
            for slot in slots
        ]

    @function_tool
    async def move_appointment(self, ctx: RunContext[CallState], slot_id: str) -> str:
        """Move the appointment to one of the free times. Only after the caller clearly agreed.

        The moved appointment is already confirmed; do not call `confirm_appointment` after this.

        Args:
            slot_id: The `slot_id` of a time returned by `find_free_slots` in this call.
        """
        state = ctx.userdata
        if slot_id not in state.offered_slot_ids:
            state.record("move_refused", slot_id=slot_id)
            raise ToolError(
                "That time was not offered in this call. Call `find_free_slots` and offer only "
                "the times it returns."
            )
        try:
            moved = state.clinic.move(self._appointment(state).id, slot_id)
        except ClinicError as exc:
            raise ToolError(f"The move did not go through: {exc}.") from exc
        state.offered_slot_ids.discard(slot_id)
        state.record("moved", appointment_id=moved.id, slot_id=slot_id)
        return f"Moved to {say_when(moved.start, state.now)} with {moved.practitioner}."

    @function_tool
    async def cancel_appointment(self, ctx: RunContext[CallState]) -> str:
        """Cancel the appointment. Only after the caller clearly agreed."""
        state = ctx.userdata
        cancelled = state.clinic.cancel(self._appointment(state).id)
        state.record("cancelled", appointment_id=cancelled.id)
        return "The appointment is cancelled."

    @function_tool
    async def confirm_appointment(self, ctx: RunContext[CallState]) -> str:
        """Record that the patient will attend the appointment as it stands.

        Only when the caller has said, in so many words, that they are coming. A caller
        who says goodbye or "that's all" has not confirmed anything.
        """
        state = ctx.userdata
        confirmed = state.clinic.confirm(self._appointment(state).id)
        state.record("confirmed", appointment_id=confirmed.id)
        return f"Confirmed for {say_when(confirmed.start, state.now)}."

    @function_tool
    async def take_message(self, ctx: RunContext[CallState], message: str) -> str:
        """Leave a message for the clinic team about anything you cannot do yourself.

        Args:
            message: What the patient wants the clinic to know or do, in their words.
        """
        state = ctx.userdata
        state.clinic.leave_message(self._patient.full_name, message, self._patient.id)
        state.record("message_taken", patient_id=self._patient.id)
        return "The message has been passed to the clinic team."
