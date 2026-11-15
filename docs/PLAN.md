# Plan

Each phase is a small set of reviewable changes, ends with a plain-language explanation, and updates [VERIFICATION.md](VERIFICATION.md). Decisions that shape the design get an ADR.

## What is being built

Quillbrook Physio (fictional) has a phone receptionist, Emily.

- **Inbound.** A patient calls. Emily works out which language they speak, checks who they are, and helps them confirm, move or cancel an appointment, or takes a message.
- **Outbound.** Emily calls a patient about tomorrow's appointment and does the same.
- **During the call** she uses tools: find free slots, reschedule, cancel, confirm, take a message, hand over to a person.

## Standing constraints

- **Mock data only.** No real patient data, ever.
- **Cheap by construction.** Nothing is left running. Every call has a length limit and there is a daily cap.
- **Only the owner's number.** No call is placed to, or answered from, a number outside an allowlist.
- **Proven, not claimed.** A capability is listed as working only with the run that showed it.

## Phases

### Phase 0: foundation (done)

Project skeleton, pinned agent framework, the four languages as data, CI with a single required check, this plan, and a receptionist that holds a text conversation through the framework.

Acceptance: unit tests pass; a text conversation runs against the real model.

### Phase 1: a voice, and tools

The worker that LiveKit dispatches calls to. Speech to text, a language model and text to speech, in English. The conversation as an explicit flow (who is calling, what they want, do it, confirm it, close). Tools against a mock clinic: find slots, reschedule, cancel, confirm, take a message, end the call.

Acceptance: a spoken conversation, in a browser or the terminal, in which a patient moves an appointment and the mock clinic's record changes. Tests drive the same conversation in text and assert on the tool calls.

### Phase 2: acting safely, and keeping records

A tool gateway between the model and the clinic: each call gets a capability limited to one patient; free slots are handed out as server-issued ids, so a time that was not offered cannot be booked; a change is held, read back, and committed only after a clear yes; every action is logged. Identity is checked with a second factor (date of birth) before any tool unlocks. Calls, transcripts and actions are stored in Postgres. After each call a check compares what was done with what was said.

Acceptance: a caller who fails the identity check can do nothing; a prompt-injection attempt cannot book an unlisted time; every committed change has a logged confirmation.

### Phase 3: evals and latency

Text-level conversations with scripted and simulated patients, graded on task completion and tool use, gating CI. Then callers who speak real audio into a real room, with background noise, accents and interruptions. Per-turn latency (how long the caller waits for a reply), reported as median and 95th percentile.

Acceptance: a results table in the README, reproducible with one command.

### Phase 4: a real phone

A phone number on a SIP trunk, routed to the worker by a dispatch rule. Outbound calls with answering-machine detection. Handing a call over to a person. The allowlist, the per-call length limit and the daily cap.

Acceptance: inbound and outbound calls on a real handset; a call from a number that is not allowed is turned away.

### Phase 5: four languages

English, Mexican Spanish, Dutch and Bosnian. Language chosen at the start of the call and switchable during it. A table of which speech services handle which language, decided by measurement. Evals in every language.

Known risk: Bosnian. The speech-to-text plugin used for English lists Dutch and Spanish but not Bosnian, so Bosnian needs a different provider, and its quality has to be judged by a native speaker.

Acceptance: the evals pass in all four languages, with per-language results published.

### Phase 6: one model instead of three

The same receptionist, tools and flow on a speech-to-speech model, which hears and speaks directly instead of going through text. Compared with the three-service chain on latency, task completion and cost.

Acceptance: a written comparison with numbers, and a recommendation.

### Phase 7: packaging

A container for the worker, a short deployment guide, traces with personal data filtered out, and a README a stranger can follow.
