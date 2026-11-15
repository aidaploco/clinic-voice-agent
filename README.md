# Clinic Voice Agent

A multilingual phone receptionist for a fictional physiotherapy clinic, built on [LiveKit Agents](https://docs.livekit.io/agents/). Patients call (or are called) to confirm, move or cancel an appointment, in English, Mexican Spanish, Dutch or Bosnian.

> **This is a demo project.** "Quillbrook Physio" and its receptionist "Emily" are fictional, and every patient, appointment and slot is invented data.

**Status: Phase 1.** Emily speaks English, checks who is calling, and can confirm, move or cancel an appointment in a mock clinic through tools. No phone number yet, no identity check beyond a name, and one language. [docs/PLAN.md](docs/PLAN.md) has the phases; [docs/VERIFICATION.md](docs/VERIFICATION.md) records what has been proven by running it and what is still assumed.

## What it is going to be

- **An agent that acts during the call.** She looks up free slots and changes appointments live, through a tool gateway that limits each call to one patient's records and asks for a spoken confirmation before anything is committed.
- **Four languages**, each with its own evaluation results.
- **Measured, not claimed.** Simulated callers, speaking real audio with noise and interruptions, are graded on whether the task was done and how long each reply took.
- **Two ways of building the voice,** compared with numbers: a chain of speech-to-text, a language model and text-to-speech, and a single speech-to-speech model.

[ADR-0002](docs/adr/0002-architecture.md) describes the design.

## Talk to it

Requires [uv](https://docs.astral.sh/uv/) and two API keys in `.env` (copy `.env.example`): Deepgram and OpenAI.

```bash
uv sync
uv run python scripts/preflight.py                    # is every service answering?
uv run python -m clinic_voice_agent.worker console    # talk to her in this terminal
```

`console` uses your computer's microphone and speakers. You are the patient **Alex Rivera**, with a shoulder physiotherapy appointment on the next working day. Give your name, then try moving the appointment, asking for a time she did not offer, or cancelling. Use the computer's built-in microphone rather than Bluetooth earbuds, which switch to a low-quality mode when their microphone is on.

Each call writes a record to `recordings/`: the transcript, what the tools did, the appointment afterwards, why the call ended, any service errors, and how long each reply took.

**If she goes quiet,** run the preflight. It makes one tiny request to each service and reports, in the provider's own words, one that has run out of credit or is down. Speech has more than one provider for this reason: when the first fails the next takes over, and if none can speak she ends the call rather than staying on the line in silence.

### Without a microphone

A scripted caller speaks into a real room in your LiveKit project and prints the call's record. It needs `LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` in `.env`.

```bash
uv run python -m clinic_voice_agent.worker start               # terminal 1
uv run python scripts/audio_caller.py "My name is Alex Rivera." "I can't make it. What other times do you have?"
```

## Tests

```bash
uv run pytest tests/unit          # no network, no keys
uv run pytest tests/behaviour     # whole conversations against the real model; needs OPENAI_API_KEY
uv run ruff check . && uv run ruff format --check .
```

The behaviour tests hold complete conversations in text and assert on what the tools did: that a patient can move their appointment, that a caller who is not a patient cannot reach the appointment tools, that a time which was never offered cannot be booked, and that a caller who hangs up undecided changes nothing.

## Changing the repo

Changes reach `main` through a pull request. CI is one workflow whose summary check, `ci-success`, fails if any job did.

```bash
git config core.hooksPath .githooks     # once per clone: refuses a direct push to main
```

## License

No license is granted. The source is published so it can be read and reviewed; please do not copy, redistribute, or reuse it without permission. All rights reserved.
