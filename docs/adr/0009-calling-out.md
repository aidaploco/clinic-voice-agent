# ADR-0009: Emily calling the owner

Status: accepted, 2026-11-15. Built and tested; the refusal path is proven against LiveKit, a real outbound call is not yet (VERIFICATION O29).

## Context

Everything so far waits to be called. Calling out is different in kind: it rings a real phone, costs money by the minute, and a mistake (a wrong number, a ringing phone with nobody on the other end of the line) is something a person feels. It is also the one feature that could be turned into a way to spend the owner's money or reach someone else.

## Decision

**Only the owner is ever dialled.** The number comes from `ALLOWED_NUMBERS`. The endpoint takes no number, so nothing the browser sends can change who is dialled; if several are allowed, a request may only choose among them. An empty list dials nobody.

**Emily is in the room before the phone rings.** The server dispatches her into a new room and polls until she has joined (`AGENT_WAIT_SECONDS`, 10). If no worker is running, or the one running is at its concurrency cap, nothing is dialled and the room is removed. This is what stops the worst failure: answering a ringing phone and hearing nothing.

**The call is bounded.** The phone rings for `RING_SECONDS` (30) at most and the call may last `MAX_CALL_SECONDS`, both set on the dial request itself, so LiveKit enforces them as well as the worker. The day's cap applies before anything starts. A call nobody answers removes its room.

**One attempt at a time, and a second click does not ring twice.** The endpoint holds a lock; the page asks "Ring your phone now?" and dials only on the second click.

**The worker admits the party it dialled by the identity it gave them.** The dispatch carries `{"direction": "outbound"}`; the participant's identity starts with `phone-out-`, which only the server that dialled can have assigned. If the network shows a number and it is not allowed, the call is refused anyway.

**She says who is calling before anything else.** The outbound opening is "this is Emily, the automated assistant at Quillbrook Physio, calling about an appointment", then it asks for a name. It reveals nothing about any patient or appointment: whoever answers may not be the patient, and the identity check comes first, as on every call.

## Consequences

- There is no answering-machine detection. Because only the owner's own number is dialled, a voicemail is the owner's own, but Emily would still speak to it. A real detector would be needed before dialling anyone else, and is not built.
- A page click while another call is running ends in "no worker joined", not a second call.
- The page cannot tell the wait for Emily from the ringing: it shows one message until the call is answered or refused.
- Whether the network reports the callee's number on an outbound call is not known (O29); the identity check does not depend on it.
- Each outbound call is billed by the telephone provider for as long as it lasts.
