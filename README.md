# Clinic Voice Agent

A multilingual phone receptionist for a fictional physiotherapy clinic, built on [LiveKit Agents](https://docs.livekit.io/agents/). Patients call (or are called) to confirm, move or cancel an appointment, in English, Mexican Spanish, Dutch or Bosnian.

> **This is a demo project.** "Quillbrook Physio" and its receptionist "Emily" are fictional, and every patient, appointment and slot is invented data.

**Status: Phase 2.** Emily speaks English, checks the caller's name and date of birth, and can confirm, move or cancel an appointment in a mock clinic. Every change goes through a gateway that reads it back and waits for a clear yes, and every call is recorded and reviewed afterwards. No phone number yet, and one language. [docs/PLAN.md](docs/PLAN.md) has the phases; [docs/VERIFICATION.md](docs/VERIFICATION.md) records what has been proven by running it and what is still assumed.

## What it is going to be

- **An agent that acts during the call.** She looks up free slots and changes appointments live, through a tool gateway that limits each call to one patient's records and asks for a spoken confirmation before anything is committed.
- **Four languages**, each with its own evaluation results.
- **Measured, not claimed.** Simulated callers, speaking real audio with noise and interruptions, are graded on whether the task was done and how long each reply took.
- **Two ways of building the voice,** compared with numbers: a chain of speech-to-text, a language model and text-to-speech, and a single speech-to-speech model.

[ADR-0002](docs/adr/0002-architecture.md) describes the design, and [ADR-0003](docs/adr/0003-acting-safely.md) how the agent is kept from doing the wrong thing on a caller's say-so.

## Talk to it

Requires [uv](https://docs.astral.sh/uv/) and two API keys in `.env` (copy `.env.example`): Deepgram and OpenAI.

```bash
uv sync
uv run python scripts/preflight.py                    # is every service answering?
uv run python -m clinic_voice_agent.worker console    # talk to her in this terminal
```

`console` uses your computer's microphone and speakers. You are the patient **Alex Rivera**, born **14 March 1990**, with a shoulder physiotherapy appointment on the next working day. Give your name and date of birth, then try moving the appointment, asking for a time she did not offer, saying "hmm, wait" when she reads a change back, or giving the wrong date of birth three times. Use the computer's built-in microphone rather than Bluetooth earbuds, which switch to a low-quality mode when their microphone is on.

Each call writes a record to `recordings/`: the transcript, every request the gateway allowed or refused, the review of the call, the appointment afterwards, why the call ended, any service errors, and how long each reply took.

To store calls in Postgres as well, start the local database and set `DATABASE_URL` (see `.env.example`). The worker creates the tables when it starts.

```bash
docker compose up -d db      # start; `docker compose down` stops it
```

**If she goes quiet,** run the preflight. It makes one tiny request to each service and reports, in the provider's own words, one that has run out of credit or is down. Speech has more than one provider for this reason: when the first fails the next takes over, and if none can speak she ends the call rather than staying on the line in silence.

### Without a microphone

A scripted caller speaks into a real room in your LiveKit project and prints the call's record. It needs `LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` in `.env`.

```bash
uv run python -m clinic_voice_agent.worker start               # terminal 1
uv run python scripts/audio_caller.py "My name is Alex Rivera." "The fourteenth of March, nineteen ninety." "I need to cancel my appointment." "Yes, cancel it."
```

## Tests

```bash
uv run pytest tests/unit          # no network, no keys
uv run pytest tests/behaviour     # whole conversations against the real model; needs OPENAI_API_KEY
uv run pytest tests/store         # needs TEST_DATABASE_URL; the file's first lines say how
uv run ruff check . && uv run ruff format --check .
```

The unit tests cover the gateway's rules with no model involved: what an unverified caller can do (nothing), which times can be booked, and when a change may be committed. The behaviour tests hold complete conversations in text and assert on what the gateway allowed and refused: a patient moves an appointment and the yes is on record; a caller who fails the identity check gets nowhere, even with the right answer on the fourth try; an injected instruction cannot book a time that was not offered; a caller who hesitates at the read-back changes nothing.

### Evals

```bash
uv run python -m evals.run             # twelve conversations, three times each; needs OPENAI_API_KEY
```

Scripted callers and callers played by a second model (an impostor, someone who changes their mind, someone who insists on a time that does not exist) talk to the receptionist in text. Each conversation is graded on what the gateway's log and the clinic's records show afterwards, not on her wording. `uv run python -m evals.review` measures the post-call review itself on calls whose right answer is known (does it flag an agent that misreports what it did, and does it leave truthful calls alone). The scenarios are in [evals/scenarios.yaml](evals/scenarios.yaml). CI runs them with `--gate 0.9`: a change is blocked if any run of a safety scenario lets the wrong person in or changes an appointment it should not have, or if fewer than 90% of runs pass.

## Changing the repo

Changes reach `main` through a pull request. CI is one workflow whose summary check, `ci-success`, fails if any job did.

```bash
git config core.hooksPath .githooks     # once per clone: refuses a direct push to main
```

## License

No license is granted. The source is published so it can be read and reviewed; please do not copy, redistribute, or reuse it without permission. All rights reserved.
