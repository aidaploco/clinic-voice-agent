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

### Phase 1: a voice, and tools (done; the owner has not yet spoken to it)

The worker that LiveKit dispatches calls to. Speech to text, a language model and text to speech, in English. The conversation as an explicit flow (who is calling, what they want, do it, confirm it, close). Tools against a mock clinic: find slots, reschedule, cancel, confirm, take a message, end the call.

Acceptance: a spoken conversation, in a browser or the terminal, in which a patient moves an appointment and the mock clinic's record changes. Tests drive the same conversation in text and assert on the tool calls.

Status: met with a scripted caller speaking real audio through LiveKit Cloud (VERIFICATION rows 6 to 16). The owner's first spoken call failed, which led to speech having a fallback provider, a call that cannot be served being ended rather than left silent, a preflight check, and a shorter wait before replying; a person has not yet repeated the call since. Found along the way and carried forward: replies take about 1.6 seconds, and up to 2.4 when a tool runs, which is the main target of Phase 3; and the rule "change nothing the caller did not ask for" is a prompt instruction until the gateway of Phase 2 enforces it.

### Phase 2: acting safely, and keeping records (done)

A tool gateway between the model and the clinic: each call gets a capability limited to one patient; free slots are handed out as server-issued ids, so a time that was not offered cannot be booked; a change is held, read back, and committed only after a clear yes; every action is logged. Identity is checked with a second factor (date of birth) before any tool unlocks. Calls, transcripts and actions are stored in Postgres. After each call a check compares what was done with what was said.

Acceptance: a caller who fails the identity check can do nothing; a prompt-injection attempt cannot book an unlisted time; every committed change has a logged confirmation.

Status: met (VERIFICATION rows 17 to 27; [ADR-0003](adr/0003-acting-safely.md)). The rules are code in the gateway and are tested without a model; conversations with the real model and scripted voice calls show them holding. Carried forward: a turn that commits a change takes over three seconds; the model sometimes proposes a change the caller did not ask for, which the read-back catches; replies after a tool call took about 3.5 seconds in the owner's own call.

### Phase 3: evals and latency

Text-level conversations with scripted and simulated patients, graded on task completion and tool use, gating CI. Then callers who speak real audio into a real room, with background noise, accents and interruptions. Per-turn latency (how long the caller waits for a reply), reported as median and 95th percentile.

Acceptance: a results table in the README, reproducible with one command.

Status: started. The text-level suite exists (`evals/`, VERIFICATION row 29): twelve conversations, scripted and simulated, graded on what the gateway and the clinic's records show. It gates CI with a rule rather than equality (every critical scenario safe in every run, 90% overall; row 30). The yes-check is measured on 24 cases and the post-call review on 12 seeded calls (rows 28 and 31). Latency: measured (VERIFICATION O1, O14): replies take about 2.1 seconds, because nearly every turn runs the model twice; tools that speak their own line now skip the second call, effect not yet measured from the caller's side. Still to do: caller-side latency measurement, the audio-level callers with noise and interruptions, and the README table.

### Phase 4: a browser page, then a real phone

In this order, each a set of reviewable changes:

1. **A browser page** ([ADR-0004](adr/0004-browser-ui.md), built with React and TypeScript per [ADR-0005](adr/0005-react-frontend.md)): a button to start a call, the live transcript, the gateway's allowed and refused requests, and the review after hang-up. Run locally, with a screenshot in the README. The per-call length limit and the daily cap, which the worker does not yet enforce, come first.
2. **Inbound calls.** A phone number on a SIP trunk, routed to the worker by a dispatch rule. A call from a number that is not on the allowlist is turned away.
3. **Outbound calls** (done): the page rings the owner's phone, and only the owner's number can be dialled ([ADR-0009](adr/0009-calling-out.md); VERIFICATION row 40). Answering-machine detection is not built.
4. **Handing a call over to a person.**

Acceptance: a call completed from the page; inbound and outbound calls on a real handset; a call from a number that is not allowed is turned away.

Status: the page is built and merged (VERIFICATION O17, O20, O21). A container image and `docker compose up` for the worker and the page ([ADR-0006](adr/0006-containers.md)) were pulled forward from Phase 7. Inbound calls ([ADR-0007](adr/0007-inbound-calls.md)): the caller allowlist, the worker's gate and the tool that points the phone line at Emily are built and tested; pointing the live line at her and a real call from the owner's phone are next. Guards that do not depend on the model (silence, calls at once, a deaf transcriber) are in place before outbound calls ([ADR-0008](adr/0008-call-guards.md)); the call list in the page is done (VERIFICATION row 38).

### Phase 5: four languages

English, Mexican Spanish, Dutch and Bosnian. Language chosen at the start of the call and switchable during it. A table of which speech services handle which language, decided by measurement. Evals in every language.

Known risk: Bosnian. The speech-to-text plugin used for English lists Dutch and Spanish but not Bosnian, so Bosnian needs a different provider, and its quality has to be judged by a native speaker.

Acceptance: the evals pass in all four languages, with per-language results published.

### Phase 6: one model instead of three

The same receptionist, tools and flow on a speech-to-speech model, which hears and speaks directly instead of going through text. Compared with the three-service chain on latency, task completion and cost.

Acceptance: a written comparison with numbers, and a recommendation.

### Phase 7: packaging

A container for the worker, a short deployment guide, traces with personal data filtered out, and a README a stranger can follow.
