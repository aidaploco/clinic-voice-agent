# Clinic Voice Agent

A multilingual phone receptionist for a fictional physiotherapy clinic, built on [LiveKit Agents](https://docs.livekit.io/agents/). Patients call (or are called) to confirm, move or cancel an appointment, in English, Mexican Spanish, Dutch or Bosnian.

> **This is a demo project.** "Quillbrook Physio" and its receptionist "Emily" are fictional, and every patient, appointment and slot is invented data.

**Status: foundation.** The project skeleton, the plan and a first text-only receptionist exist. She cannot use tools, speak or take a phone call yet. [docs/PLAN.md](docs/PLAN.md) has the phases; [docs/VERIFICATION.md](docs/VERIFICATION.md) records what has been proven by running it and what is still assumed.

## What it is going to be

- **An agent that acts during the call.** She looks up free slots and changes appointments live, through a tool gateway that limits each call to one patient's records and asks for a spoken confirmation before anything is committed.
- **Four languages**, each with its own evaluation results.
- **Measured, not claimed.** Simulated callers, speaking real audio with noise and interruptions, are graded on whether the task was done and how long each reply took.
- **Two ways of building the voice,** compared with numbers: a chain of speech-to-text, a language model and text-to-speech, and a single speech-to-speech model.

[ADR-0002](docs/adr/0002-architecture.md) describes the design.

## Try the first version

Requires [uv](https://docs.astral.sh/uv/) and an OpenAI API key in `.env` (copy `.env.example`).

```bash
uv sync
uv run python scripts/smoke_text.py "Hi, who am I speaking with?" "Can you move my appointment?"
```

This holds a short text conversation with the receptionist through the agent framework. It makes a few real model calls.

## Tests

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Changing the repo

Changes reach `main` through a pull request. CI is one workflow whose summary check, `ci-success`, fails if any job did.

```bash
git config core.hooksPath .githooks     # once per clone: refuses a direct push to main
```

## License

No license is granted. The source is published so it can be read and reviewed; please do not copy, redistribute, or reuse it without permission. All rights reserved.
