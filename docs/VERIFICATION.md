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

## Assumed (to be proven in the phase named)

| # | Claim | Prove in |
|---|---|---|
| A1 | A worker registers with LiveKit Cloud, is dispatched a call, and holds a spoken conversation | Phase 1 |
| A2 | The framework's test runner can assert on tool calls precisely enough to gate CI | Phase 1 |
| A3 | The built-in date-of-birth task is good enough for the identity step, or can be replaced | Phase 2 |
| A4 | Answering-machine detection works on real outbound calls | Phase 4 |
| A5 | Some speech-to-text and text-to-speech provider handles Bosnian well enough for a native speaker | Phase 5 |
| A6 | A speech-to-speech model can run the same tools and flow | Phase 6 |
| A7 | CI passes on GitHub; it has only been run locally (lint, tests, actionlint) | first push |
