# ADR-0013: Traces without personal data

Status: accepted, 2026-11-16.

## Context

A trace shows where a call's time went, which is what one wants when a call feels slow. By default it is also a copy of the conversation: what the caller said (including a date of birth), what the model said, the arguments of every tool call, and, for a phone call, the caller's number in the room's name.

## Decision

- Tracing is off unless asked for: `TRACE_ENDPOINT` (an OpenTelemetry collector; Phoenix, in `docker compose --profile traces`) or `TRACE_FILE` (JSON lines, for checking). The setting has its own name, not the standard `OTEL_*` variables, because those may point at some other project's collector.
- **Two filters stand in front of every exporter.** The framework's own (`allow_pii=False`) strips what it knows to be personal. Ours (`tracing.py`) runs after it and rewrites what is left: it takes out phone-shaped and email-shaped text and home-folder paths, and drops attributes named for a phone, a room, a participant, an identity or a stack trace.
- **The allowance is checked, not trusted.** A scripted audio call through the real worker wrote its spans to a file. 162 spans, 82 attribute names; searched for the patient's name, date of birth, the times, the practitioners' names and her words: nothing. One thing was found that the framework does not strip: a stack trace in an event-loop-blocked span, holding the home-folder path of whoever ran the worker. The second filter removes it.
- The call's own record keeps the details a person needs (the transcript, the timeline); the trace is for timing and structure, not for reading the call.

## Not done

Linking a call's record to its trace (the trace id is not in the record). Sampling. A phone call through the filters (a call by phone has more identifying attributes than a browser one; the filter drops them by name and by shape, but no phone call's spans have been captured and read).

## Consequences

- A trace shows that a turn was slow and which stage was; to see why, open the record.
- A new framework version may add attributes. The file exporter and `python -m evals.pii_audit` are how to recheck.
