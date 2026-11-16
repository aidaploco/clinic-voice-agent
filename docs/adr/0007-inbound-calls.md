# ADR-0007: Taking phone calls

Status: accepted, 2026-11-15. Built and unit-tested; not yet proven with a real call (VERIFICATION O23).

## Context

A phone call arrives at a Twilio number, is passed to LiveKit's SIP service, and a dispatch rule turns it into a room. This worker answers a room only when it is dispatched to it by name, so a rule that names no agent produces a room nobody joins. A read-only check on 2026-11-15 found the project's rule naming no agent. A dispatch rule names its answerers, so changing it changes who is called for that number.

## Decision

**Two gates against unwanted callers.** The first is the allowed-numbers list on the LiveKit inbound trunk, which refuses most callers before any room exists. The second is in the worker: after joining the room it reads the caller's number from the SIP participant and admits the call only if it is in `ALLOWED_NUMBERS` (E.164, comma-separated). It fails closed: an empty list, a missing number or an unreadable one admits no phone caller, and a malformed list stops the worker at startup rather than being quietly ignored. A refused call costs nothing: no speech, no model, no record, and the log holds the last three digits only.

**This is a limit on cost and abuse, not proof of who is calling.** Caller ID can be spoofed. Identity still takes a name and a date of birth, behind the gateway, and the data is invented.

**The browser page needs no number.** It is the owner's own machine behind a localhost-only server, and is admitted without one.

**The rule is changed by a tool that can undo itself.** `scripts/setup_inbound.py` is a dry run unless given `--apply`; it checks that the caller's number is not hidden by the rule (or the worker could not see it), that `ALLOWED_NUMBERS` is set, and that it matches the trunk's list; it saves the rule as it was before replacing it, and `--revert --apply` restores it exactly. It never prints a number.

**Limits apply as to every call.** The length limit and the daily cap are enforced in the worker, so a phone call inherits them.

## Consequences

- Changing the rule changes who is dispatched for that number. The tool saves the rule it replaces, and `--revert --apply` restores it with one command.
- The "turned away" behaviour cannot be proven with a real second phone (the owner has none to spare); it is covered by unit tests of the decision, and the trunk's list is the live first gate.
- Twilio's side (the number's origination address pointing at LiveKit's SIP service) is not changed or checked by code; it is the owner's account.
- Handing a call over to a person (`transfer_sip_participant`) and outbound calls (`add_sip_participant`) come next, on the same trunk.
