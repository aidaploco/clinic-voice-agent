# ADR-0008: Guards that do not depend on the model

Status: accepted, 2026-11-15. The silence and concurrency guards are proven with real calls; the deaf-transcriber guard is tested only as logic (VERIFICATION O25).

## Context

A call costs money for as long as it is open, whatever is happening on it. A phone line opens the door to calls nobody is watching: a caller who says nothing, a second caller at once, or a transcriber that stops answering with no error and leaves the agent deaf. None of these can be left to the prompt.

## Decision

All limits are enforced by the worker, so every way into it (the page, a container, a phone) inherits them, and none depends on what the model says.

| Guard | Setting | What happens |
|---|---|---|
| Length of a call | `MAX_CALL_SECONDS` (300) | spoken goodbye, hang up |
| Calls per day | `DAILY_CALL_CAP` (25) | the caller is told, hung up on, no record |
| Calls at once | `MAX_CONCURRENT_CALLS` (1) | the worker reports itself full and is given no new calls |
| Silence | `SILENCE_SECONDS` (25) | when both sides have been quiet that long: spoken goodbye, hang up |
| A deaf transcriber | built in | two stretches of real speech in a row with no words back: spoken apology, hang up |

**Concurrency uses the framework's own load signal.** The worker's load is calls running over the cap; above the framework's production threshold (0.7) it marks itself unavailable. This applies under `worker start` (the page, containers and phone), not under `dev` or `console`.

**Deafness uses the framework's own event**, raised when the voice detector heard speech and no transcript followed, not a timer of ours. A single event never ends a call: a cough is speech to the detector, and the framework withholds audio from the transcriber on purpose at times, so it takes two in a row, each at least 0.8 seconds of speech, and any real transcript starts the count again.

## Consequences

- At the cap the next caller is not refused: they are not answered until a call ends. For a phone caller that is silence. A "we are busy" message would need a second process that is always available; not done.
- The concurrency cap counts calls running in this worker. Two workers have two caps.
- The deaf-transcriber guard has not been seen to fire on a real failure, because a transcriber that fails silently cannot be made to on demand. A normal call and a silent call both behaved correctly with it running.
