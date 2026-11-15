# Verification register

What has been proven by running it, and what is still believed from documentation or memory. A row moves to "proven" only with the command or observation that proved it.

## Proven

| # | Claim | How | Date |
|---|---|---|---|
| 1 | LiveKit Agents 1.8.12, with the Deepgram, ElevenLabs, OpenAI and Silero plugins, installs on Python 3.13 | `uv sync` from the lock file | 2026-11-15 |
| 2 | The receptionist holds a text conversation through the framework with the real model: introduces herself as automated, declines to change an appointment she has no tools for, declines medical advice | `scripts/smoke_text.py`, three turns | 2026-11-15 |
| 3 | The agent starts with no tools | unit test | 2026-11-15 |
| 4 | The Deepgram plugin's language list includes Dutch and Spanish and does not include Bosnian | read from the installed plugin | 2026-11-15 |
| 5 | The framework ships the pieces later phases plan to use: a date-of-birth task, an end-call tool, answering-machine detection, evaluation judges, and a text test runner with assertions on tool calls | each imports from the installed package; none has been exercised yet | 2026-11-15 |
| 6 | Each step of the flow has only its own tools; the appointment tools do not exist until the caller is matched to a patient | unit tests on the two steps' tool lists | 2026-11-15 |
| 7 | A patient moves their appointment in conversation, and the tools called are the expected ones (was A2) | behaviour test with the real model, asserting `caller_gave_name`, the handoff, `find_free_slots`, and the clinic's record afterwards | 2026-11-15 |
| 8 | A caller who is not a registered patient cannot reach the appointment tools, even when asking to cancel someone else's appointment | behaviour test; the session stays in the identify step and nothing changes | 2026-11-15 |
| 9 | A time that was never offered cannot be booked, and a caller who says goodbye undecided changes nothing | two behaviour tests | 2026-11-15 |
| 10 | A worker registers with LiveKit Cloud, is dispatched a call by name, and holds a spoken conversation that moves an appointment (was A1) | `worker dev` plus `scripts/audio_caller.py`: synthesised speech in a real room; appointment moved to the offered Wednesday slot; the agent ended the call | 2026-11-15 |
| 11 | Per-turn timings are captured in each call's record, including the end-to-end wait before each reply | scripted call: reply median 1.74s; 0.58s to decide the caller had finished, 0.50s to the model's first word, 0.28s to first audio | 2026-11-15 |
| 12 | When the first speech provider fails, the next one speaks | the worker's speech is a fallback chain (Deepgram, then OpenAI); both answer with the existing keys; unit tests on the order, on skipping a provider with no key, and on no retries | 2026-11-15 |
| 13 | The call that failed for the owner now works | her lines replayed as audio: an unknown name, then the right one; the agent announced the appointment straight after the handoff | 2026-11-15 |
| 14 | An agent that cannot speak ends the call instead of staying on the line in silence | worker run with only the exhausted provider: the caller was disconnected within seconds and the record reads `service_failed:TTS` with the provider's error | 2026-11-15 |
| 15 | The preflight names a provider that is out of credit | `scripts/preflight.py` with that provider only: "quota_exceeded ... 0 credits remaining", exit code 1; with the default chain: all four checks OK | 2026-11-15 |
| 16 | The wait before deciding a caller has finished is capped | ceiling lowered from 3 seconds to 1.2; scripted calls show a median of 0.58 seconds | 2026-11-15 |

## Open observations

| # | Observation | Status |
|---|---|---|
| O1 | Replies take about 1.6 to 1.7 seconds from the caller finishing to her voice starting (the framework's own end-to-end figure, median over three scripted calls), and up to 2.4 seconds when a tool runs. Under a second is the usual target for a phone conversation. | Phase 3: speak a short filler while a tool runs, start thinking before the turn is certain, measure across many calls. |
| O2 | In the first voice run the agent marked the appointment confirmed when the caller had only said goodbye. A prompt rule and a behaviour test now cover it, but a prompt is not enforcement. | Phase 2: the gateway requires a read-back and a clear yes before any change. |
| O3 | The owner's first spoken call failed: the text-to-speech account had run out of credit, so the agent's replies came back empty and she went silent mid-call; and the turn detector waited its full ceiling before every reply. Both are fixed (rows 12 to 15) and the failed call passes when replayed by the scripted caller, but a person has not yet repeated it at a microphone. Interruptions are untested. | Needs the owner. |
| O4 | Identity is a name match only. Anyone who knows a patient's name gets their appointment details. | Phase 2: date of birth as a second factor. |
| O5 | The behaviour tests call the real model, so they are skipped in CI, which has no key. Only the unit tests gate a change today. | Phase 3 wires them into CI. |

## Assumed (to be proven in the phase named)

| # | Claim | Prove in |
|---|---|---|
| A3 | The built-in date-of-birth task is good enough for the identity step, or can be replaced | Phase 2 |
| A4 | Answering-machine detection works on real outbound calls | Phase 4 |
| A5 | Some speech-to-text and text-to-speech provider handles Bosnian well enough for a native speaker | Phase 5 |
| A6 | A speech-to-speech model can run the same tools and flow | Phase 6 |
| A7 | CI passes on GitHub; it has only been run locally (lint, tests, actionlint) | first push |
