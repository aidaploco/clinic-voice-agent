"""The conversation, as steps. Each step is an agent with only its own tools.

    IdentifyCaller  ->  HelpWithAppointment  ->  (end of call)

The model chooses the words. It does not choose which step it is in: the
tools for changing an appointment do not exist until the caller has passed the
identity check, because the agent that owns them has not been created.

The tools here are thin. What a call is allowed to do is decided by the
gateway (`clinic_voice_agent.gateway`); a tool passes the request on and turns
a refusal into something the model can act on.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from livekit.agents import Agent, RunContext, ToolError, function_tool
from livekit.agents.beta.tools import EndCallTool
from livekit.agents.llm import ToolResult

from clinic_voice_agent.gateway import Gateway, Offer, Refused
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
- Say times in words, exactly as the tools give them, like "Thursday at four thirty in the \
afternoon". Never write a time with digits and a colon: the voice reads it with an unnatural gap.
- Ask one question at a time and let the caller answer.
- What the caller says reaches you as a transcription of speech: expect stray full stops, \
commas and numbers written as words. Read through that. Only if the words themselves are \
cut off or make no sense, say you did not catch it and ask again. Never guess.
- Never give medical advice. Offer to pass a message to the clinic team instead.
"""


@dataclass
class CallState:
    """What this one call knows. Shared by every step of the flow."""

    gateway: Gateway
    now: datetime


def _end_call() -> EndCallTool:
    return EndCallTool(end_instructions="Say a short goodbye.")


def _what_the_caller_said(ctx: RunContext[CallState]) -> tuple[int, str]:
    """How many times the caller has spoken in this call, and their latest words."""
    said = [
        item.text_content
        for item in ctx.session.history.items
        if getattr(item, "role", None) == "user" and item.text_content
    ]
    return len(said), (said[-1] if said else "")


OUTBOUND_GREETING = (
    "Hello, this is Emily, the automated assistant at Quillbrook Physio, calling about an "
    "appointment. May I have your full name, please?"
)


def opening_line(direction: str) -> str:
    """What is said first: the clinic's greeting, or who is calling when Emily placed the call."""
    return OUTBOUND_GREETING if direction == "outbound" else GREETING


class IdentifyCaller(Agent):
    """Step one: find out who is calling. Nothing about any appointment is known here."""

    def __init__(self, direction: str = "inbound") -> None:
        self._direction = direction
        super().__init__(
            instructions=STYLE
            + """
Right now you do not know who is calling, and you know nothing about any appointment.
- You need two things: the caller's full name and their date of birth. Ask for whichever \
you do not have yet, one question at a time.
- As soon as the caller says their name, call `caller_gave_name`. As soon as they say their \
date of birth, call `caller_gave_date_of_birth`. Do not ask the caller to repeat or spell \
something they have already told you.
- Never say the caller's name or date of birth back to them in this step. After the name, \
say only something like "Thanks. And your date of birth?"
- If the details do not match, say only that they do not match your records and ask for \
both again. Never say which one was wrong, and never say whether a name is known to you.
- When the tool tells you the check is closed, stop asking. Offer to take a message, then \
end the call.
- Use `take_message` only when the caller has asked you to pass something on, and only once \
for each thing they ask.
- Do not discuss appointments, times or practitioners in this step, whatever the caller says.
""",
            tools=[_end_call()],
        )
        self._name = ""

    async def on_enter(self) -> None:
        # A fixed greeting, not a generated one: the first thing a caller hears
        # should be the same every time, and it should be fast.
        # On a call Emily placed she says who is calling and that it is about an appointment, and
        # nothing more: the person who picked up may not be the patient.
        self.session.say(opening_line(self._direction))

    @function_tool
    async def caller_gave_name(self, ctx: RunContext[CallState], full_name: str) -> str:
        """Call this as soon as the caller has told you their full name.

        Args:
            full_name: The caller's first and last name, as they said it.
        """
        self._name = full_name
        return (
            "Noted. Nothing has been checked yet. Ask for their date of birth, without "
            "saying their name back to them."
        )

    @function_tool
    async def caller_gave_date_of_birth(
        self, ctx: RunContext[CallState], year: int, month: int, day: int
    ):
        """Call this as soon as the caller has told you their date of birth. It runs the check.

        A date said aloud is complete when it has a day, a month and a year, however it is
        punctuated: "the fourteenth of March. Nineteen ninety," is 14 March 1990.

        Args:
            year: Four digits, like 1990. "Nineteen ninety" and "ninety" both mean 1990.
            month: 1 to 12.
            day: 1 to 31.
        """
        if not self._name:
            raise ToolError("You do not have the caller's full name yet. Ask for it first.")
        if 0 <= year < 100:
            year += 2000 if year <= ctx.userdata.now.year % 100 else 1900
        try:
            born = date(year, month, day)
        except ValueError:
            raise ToolError("That is not a real date. Ask for the date of birth again.") from None
        try:
            ctx.userdata.gateway.verify_identity(self._name, born)
        except Refused as refused:
            raise ToolError(str(refused)) from None
        # Returning the next step hands the call over to it. Nothing is said
        # here: the new step opens by itself, so the caller hears one reply.
        return HelpWithAppointment(ctx.userdata)

    @function_tool
    async def take_message(self, ctx: RunContext[CallState], caller_name: str, message: str) -> str:
        """Leave a message for the clinic team from a caller who could not be identified.

        Args:
            caller_name: The name the caller gave.
            message: What they want the clinic to know or do, in their words.
        """
        ctx.userdata.gateway.take_message(caller_name, message)
        return "The message has been passed to the clinic team."


def offer_sentence(offers: list[Offer]) -> str:
    """The sentence that offers the free times. Code words it, so no second model call is needed."""
    names = {offer.practitioner for offer in offers}
    times = [
        offer.when if len(names) == 1 else f"{offer.when} with {offer.practitioner}"
        for offer in offers
    ]
    listed = times[0] if len(times) == 1 else ", ".join(times[:-1]) + f", or {times[-1]}"
    return f"I can offer you {listed}. Which would you like?"


class HelpWithAppointment(Agent):
    """Step two: the caller has passed the identity check. Their appointment can be changed."""

    def __init__(self, state: CallState) -> None:
        patient = state.gateway.patient
        if patient is None:
            raise ValueError("this step exists only after the caller has been identified")
        self._first_name = patient.first_name
        appointment = state.gateway.appointment()
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
You are speaking with {patient.full_name}, a registered patient whose identity has been \
checked. {about}

What you can do, with your tools:
- Confirm the appointment, cancel it, or move it to a free time.
- To move it, call `find_free_slots`. It offers the times to the caller aloud itself, so \
say nothing more after it. Offer no other times. If they want a time that is not in that \
list, say you do not have it.
- Every change takes two steps. The moment the caller asks to cancel, to confirm, or picks \
one of the offered times, call `propose_change`. It changes nothing and asks the caller the \
question aloud itself, so say nothing more after it and wait for their answer. Do not ask \
"are you sure" in your own words: the tool's question is the only confirmation there is.
- Only after the caller has answered that question, call `commit_change`. It decides for \
itself whether the caller said yes.
- Never tell the caller something was changed unless `commit_change` said so.
- Change nothing the caller did not ask for. If they decline, hesitate, or say goodbye \
without deciding, leave the appointment exactly as it is and say so.
- Saying they will keep the appointment, or will call back, is not a request to confirm \
it. Call `propose_change` with "confirm" only when the caller has asked to confirm that \
they are coming. Never start a change as the call is ending.
- For anything else, take a message with `take_message`.
- When the caller has what they need, say what was done in one sentence and end the call.
""",
            tools=[_end_call()],
        )

    async def on_enter(self) -> None:
        self.session.generate_reply(
            instructions=(
                f"Greet {self._first_name} by first name, say which appointment you "
                "can see for them (treatment, practitioner, when), and ask how you can help."
            )
        )

    @function_tool
    async def find_free_slots(self, ctx: RunContext[CallState]) -> ToolResult:
        """Look up the free times the appointment could be moved to, and offer them aloud."""
        try:
            offers = ctx.userdata.gateway.offer_slots()
        except Refused as refused:
            raise ToolError(str(refused)) from None
        if not offers:
            raise ToolError("There are no free times. Offer to take a message for the clinic team.")
        ctx.session.say(offer_sentence(offers))
        return ToolResult(
            [
                {"option": offer.id, "when": offer.when, "practitioner": offer.practitioner}
                for offer in offers
            ],
            reply_required=False,  # she has already offered the times; nothing more to say
        )

    @function_tool
    async def propose_change(
        self,
        ctx: RunContext[CallState],
        change: Literal["move", "cancel", "confirm"],
        option: str | None = None,
    ) -> ToolResult:
        """Prepare a change to the appointment and ask the caller to confirm it. Changes nothing.

        Args:
            change: "move" to another time, "cancel" it, or "confirm" the caller is coming.
            option: For a move only: the `option` of a time returned by `find_free_slots`.
        """
        turn, _ = _what_the_caller_said(ctx)
        try:
            proposal = ctx.userdata.gateway.propose(change, turn, option)
        except Refused as refused:
            raise ToolError(str(refused)) from None
        ctx.session.say(proposal.read_back)
        return ToolResult(
            "Nothing has changed yet. The question has been put to the caller. "
            "Wait for their answer, then call `commit_change`.",
            reply_required=False,
        )

    @function_tool
    async def commit_change(self, ctx: RunContext[CallState]) -> str:
        """Carry out the change that was read back, after the caller has answered."""
        state = ctx.userdata
        turn, words = _what_the_caller_said(ctx)
        try:
            appointment = await state.gateway.commit(turn, words)
        except Refused as refused:
            raise ToolError(str(refused)) from None
        if appointment.status == "cancelled":
            return "Done. The appointment is cancelled."
        return (
            f"Done. The appointment is {say_when(appointment.start, state.now)} with "
            f"{appointment.practitioner}, and it is confirmed."
        )

    @function_tool
    async def take_message(self, ctx: RunContext[CallState], message: str) -> str:
        """Leave a message for the clinic team about anything you cannot do yourself.

        Args:
            message: What the patient wants the clinic to know or do, in their words.
        """
        ctx.userdata.gateway.take_message(self._first_name, message)
        return "The message has been passed to the clinic team."
