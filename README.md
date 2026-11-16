# Clinic Voice Agent

A phone receptionist for a fictional physiotherapy clinic, built on [LiveKit Agents](https://docs.livekit.io/agents/). Patients call, or are called, to confirm, move or cancel an appointment, in English, Mexican Spanish, Dutch or Bosnian. She checks who is calling, changes the clinic's records only through a gateway that enforces the rules in code, and every call is recorded, reviewed afterwards and traced. Simulated callers grade her in CI, and a browser page shows what she did and why.

> **This is a demo project.** "Quillbrook Physio" and its receptionist "Emily" are fictional, and every patient, appointment and slot is invented data. The identity check (name and date of birth) is demo-grade. The page runs on your own machine: do not expose it publicly, because every call spends speech and model credit.

![The page after a call that came in by phone: the transcript, the gateway's four decisions with the exact question asked before the change, the review, and the list of earlier calls](docs/images/page.png)

A call that came in by phone, opened from the call list. Emily moved the appointment to Friday. On the right is what the gateway decided at each step and the post-call review. Below is the list of earlier calls, including one Emily placed herself.

## What you can and cannot reproduce

| | Anyone, with their own keys | Only the owner |
|---|---|---|
| **Browser call**: the page, the transcript, the gateway's decisions, the review, the call list | Yes. Needs Docker and keys for Deepgram, OpenAI and a free [LiveKit Cloud](https://cloud.livekit.io) project. | |
| **Tests and evals**: unit tests, the page's tests, the eval conversations | Yes. The evals need an OpenAI key. | |
| **Phone calls**: dialling in, and the page's "Call my phone" button | | **Not reproducible as a demo.** They go through the owner's own telephone number and SIP line, and the code admits exactly one number, the one in `ALLOWED_NUMBERS`, in both directions. To try the phone path you would need your own telephone provider account, number and SIP trunk ([how it is set up](docs/adr/0007-inbound-calls.md)). |

That limit is on purpose: a phone number that anyone could dial would let strangers spend the owner's credit. What the phone calls proved, and when, is in [docs/VERIFICATION.md](docs/VERIFICATION.md).

## Highlights

| | |
|---|---|
| **The model asks; code decides** | Every tool is a thin wrapper around the gateway. The rules (who is allowed to change what, and only after a clear yes) live in code and are tested without a model. |
| **Four languages** | A spoken menu: say the language or, on a phone, press a key. English if nobody answers. Each language has its own speech services, wording and way of saying times. |
| **Graded by simulated callers** | Scripted and model-played callers, run three times each in CI; every safety-critical scenario must be safe in every run. |
| **Every call explains itself** | Transcript, the gateway's audit log, a post-call review, a timeline of the call, and traces with personal data removed. |
| **Honest about what is unproven** | [VERIFICATION](docs/VERIFICATION.md) records each claim with the run that showed it, and lists what is still assumed. |

## How it works

```mermaid
flowchart TB
    P["Phone (Twilio, LiveKit SIP)"] --> R(("LiveKit room"))
    B["Browser page"] --> R
    R <--> W["Worker: speech to text, model, text to speech"]
    W --> M["Language menu: speech or keypad, in code"]
    M --> F["Flow: identify, then help"]
    F -->|tool calls| G{{"Gateway: the rules, in code"}}
    G --> C[("Mock clinic")]
    G --> A["Audit log"]
    A --> V["Post-call review"]
    V --> S[("Records: JSON and Postgres")]
    S --> U["Page: call list and detail"]
    W -.spans, personal data removed.-> T["Traces (Phoenix)"]
```

- **The model asks; code decides.** Every tool is a thin wrapper around `gateway.py`. The rules live there, none of them depend on the prompt, and most are tested without a model ([ADR-0003](docs/adr/0003-acting-safely.md)).
- **Identity comes first.** Full name and date of birth, three attempts, then the check is closed. A wrong name and a wrong date get the same refusal. Nothing but taking a message works before it passes, and the date of birth never goes in the audit log.
- **One patient per call.** Passing the check gives the call a capability for one patient. Free times are handed out as ids made up for the call, so a time that was not offered cannot be booked.
- **A change takes two steps with the caller in between.** `propose_change` changes nothing and returns the question to read back. `commit_change` is refused unless the caller has spoken since, and a second model, which sees only the question and their reply, decides whether that was a clear yes.
- **Everything is logged, then reviewed.** Each request to the gateway is an audit event. After the call, two checks read the log without a model and a third compares what she told the caller with what was actually done.
- **Limits that do not depend on the model.** A call has a length limit and ends after a silence; a worker runs a set number at once; there is a daily cap; and two stretches of speech in a row with no words back end the call, except while the caller is still choosing a language ([ADR-0008](docs/adr/0008-call-guards.md)).
- **The page.** React and TypeScript ([ADR-0005](docs/adr/0005-react-frontend.md)): the live transcript, the gateway's decisions as they happen, the review, and the list of earlier calls, phone calls included.
- **Stack.** LiveKit Agents (pinned), Deepgram for hearing and as the first-choice voice, OpenAI for the model and as the backup voice, Postgres for records, Docker for running it all.

## Languages

Emily opens in English, says who she is, then offers each other language in that language's own voice ("Para continuar en español, diga español"). The caller says the language, or on a phone presses its key (1 Spanish, 2 Dutch, 3 Bosnian). With no answer she carries on in English: silence at the menu never hangs up. The menu is a step decided in code, not by the model ([ADR-0011](docs/adr/0011-languages-in-a-call.md)).

| Language | Hears | Speaks | Spoken times |
|---|---|---|---|
| English | Deepgram `nova-3` | Deepgram Aura-2 | "four thirty in the afternoon" |
| Mexican Spanish | Deepgram `nova-3` | Deepgram Aura-2 (OpenAI as backup) | "cuatro y media de la tarde" |
| Dutch | Deepgram `nova-3` | Deepgram Aura-2 (OpenAI as backup) | "half vijf 's middags" |
| Bosnian | OpenAI `gpt-4o-transcribe`, told how a date is said | OpenAI `gpt-4o-mini-tts` | "pola pet poslijepodne" |

The choice was made by measuring, not by reputation: [ADR-0010](docs/adr/0010-speech-by-language.md) has the round-trip word error of each service per language, and ADR-0011 what failed in the first live tries and why the menu is built the way it is. A speech-to-speech model was tried in place of the three services and was no faster, about four times the cost and no better to listen to, so it was not adopted ([ADR-0012](docs/adr/0012-speech-to-speech.md); the code is on the branch `phase-6-realtime`).

## What has been measured

| What | Result | Read it with |
|---|---|---|
| Conversations against the real model | 19 scenarios, 7 of them safety-critical, in four languages, run three times each in CI. The gate: every critical scenario safe in every run, and 90% overall. | Callers and grader are models, so it is a rule and not equality. |
| The yes-check (is this reply a clear yes?) | 24 cases, mostly English, with Spanish, Dutch and Bosnian replies. | Written by the author. |
| The post-call review | 14 calls with a known right answer: 0 false alarms in 64 runs on the 8 truthful calls, 0 of 48 misreports missed on the 6 that were not. | Written by the author, so optimistic. |
| Reply time as the caller feels it | Median 2.2 s, 95th percentile 3.3 s over 25 turns. The turn after a tool call is slowest. | Five spoken calls only. |
| Which transcriber hears a language name on a phone line | OpenAI told the four names: 30 of 33 clips right. Deepgram's multilingual model: 19 of 33, and Dutch 0 of 9. This is why the keypad exists. | Synthetic voices, degraded to phone quality; not real callers. |
| Real calls | A browser call, inbound and outbound phone calls, a call through the containers, and the owner's own calls in Bosnian and Dutch. | A few of each. |

[docs/VERIFICATION.md](docs/VERIFICATION.md) is the full register: what was proven by running it, the run that showed it, and what is still assumed.

## Traces, with personal data removed

![Phoenix listing the spans of one call: the model requests, the voice requests, the tool calls, the input column empty and the output column holding only model and request ids](docs/images/traces.png)

A trace of a call shows where its time went: each turn, the speech services, the model, every tool call. By default that is also a copy of the conversation, so here two filters sit in front of the exporter ([`tracing.py`](src/clinic_voice_agent/tracing.py)): the framework's own, which strips what was said, what the model said and tool arguments, and ours, which takes out anything shaped like a phone number, an email address or a home-folder path, and drops anything named for a phone, a room or a stack trace. The empty input column above is the point. The filters were checked against a scripted audio call through the real worker: none of the patient's details (name, date of birth, the times, what she said) appeared in what was exported, and a stack trace that carried a home-folder path is now removed ([ADR-0013](docs/adr/0013-traces-without-personal-data.md)).

```bash
TRACE_ENDPOINT=http://phoenix:6006 docker compose --profile traces up --build    # then http://127.0.0.1:6007
```

Every call also keeps a timeline in its own record (when the caller started and stopped speaking, what the language menu heard and chose, when words came back), which is what explained the failed live tries in ADR-0011.

## Quickstart

Requires Docker, [uv](https://docs.astral.sh/uv/) only if you run it natively, and these keys in `.env`: Deepgram, OpenAI, and the three LiveKit values of a [LiveKit Cloud](https://cloud.livekit.io) project.

```bash
cp .env.example .env         # then fill in the keys
docker compose up --build
```

| Service | Address |
|---|---|
| The page | http://127.0.0.1:8765 |
| Postgres (call records) | 127.0.0.1:54329, this machine only |
| Phoenix (traces, only with `--profile traces`) | http://127.0.0.1:6007 |

Click **Start a call**. You are the patient **Alex Rivera**, born **14 March 1990**, with a shoulder physiotherapy appointment on the next working day. After the language menu, give your name and date of birth, then try moving it, asking for a time she did not offer, saying "hmm, wait" when she reads a change back, or giving the wrong date of birth three times. Try another language by saying it. Use the computer's built-in microphone: Bluetooth earbuds switch to a low-quality mode when their microphone is on. After a change to the code, run `docker compose up --build` again, because the containers are a snapshot.

<details>
<summary>Without Docker</summary>

```bash
uv sync
(cd web && npm ci && npm run build)                   # Node 22.13 or newer
uv run python scripts/preflight.py                    # is every service answering?
uv run python -m clinic_voice_agent.worker start      # terminal 1: takes the calls
uv run python -m clinic_voice_agent.web               # terminal 2: the page
uv run python -m clinic_voice_agent.worker console    # or talk to her in this terminal
```

`docker compose up -d db` starts only the database, and `DATABASE_URL` (see `.env.example`) makes the worker store calls there too. Without it, a call's record is a JSON file in `recordings/`. For development, `cd web && npm run dev` serves the page on port 5173.

</details>

### By phone (the owner's setup)

Set `ALLOWED_NUMBERS` to your number in E.164 form (`+`, country code, number), point your telephone provider's number at your LiveKit project's SIP address, then:

```bash
uv run python scripts/setup_inbound.py            # dry run: shows what would change
uv run python scripts/setup_inbound.py --apply    # point the line's dispatch rule at Emily (saves the old rule)
uv run python scripts/setup_inbound.py --revert --apply   # put it back
```

The page's **Call my phone** button rings the number in `ALLOWED_NUMBERS` once you confirm (it never takes a number from the page), and needs `SIP_OUTBOUND_TRUNK_ID`. The telephone provider bills each call, inbound and outbound, for as long as it lasts.

## Tests and evals

```bash
uv run pytest tests/unit                  # no network, no model
uv run pytest tests/behaviour             # real conversations, needs OPENAI_API_KEY
(cd web && npm test)                      # the page
uv run python -m evals.run --repeat 3 --gate 0.9     # the eval conversations, as CI runs them
uv run python -m evals.review --repeat 8             # the post-call review against known answers
uv run python scripts/measure_latency.py --calls 5   # spoken calls; the worker must be running
uv run python scripts/choice_probe.py                # which transcriber hears a language name
uv run python -m evals.pii_audit                     # is anything private in the repo (see below)
```

One required check, `ci-success`, waits for every job: a secret scan over the whole history, a workflow lint, the Python tests, the page (type-check, lint, tests, build, an audit of what ships), the container image (built and smoke-tested), and the evals. The evals use scripted and simulated callers, graded on what the gateway's log and the clinic's records show, not on what she said. A scenario marked critical must be safe in every run, because an occasional lapse is exactly the failure that matters; a run that never reached the lock is reported as inconclusive and counts against the pass rate, not as unsafe.

## Privacy of this repository

The data in the repository is invented: the clinic, the patients, the appointments, the phone numbers in tests (invented, in the 555 exchange). The owner's real values (keys, the phone line, the telephone number) live only in `.env`, which is not committed, and in records on the owner's disk, which are not either. `python -m evals.pii_audit` checks that: it takes every private value from `.env`, plus names or addresses given at run time, and looks for each in every tracked file, in the whole git history and in the GitHub page (pull requests, comments, description), without ever printing a value. A phone call's record names the call by a hash, not by the room name, which holds the caller's number. See [VERIFICATION O28 and O52](docs/VERIFICATION.md) for the runs.

## Configuration

Settings load from the environment or `.env` (see `src/clinic_voice_agent/settings.py`).

| Variable | Default | Purpose |
|---|---|---|
| `DEEPGRAM_API_KEY`, `OPENAI_API_KEY` | required | Hearing and thinking (and the voice) |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | required for `start` | Your LiveKit project |
| `LLM_MODEL`, `STT_MODEL` | `gpt-4.1-mini`, `nova-3` | The model and the transcriber |
| `TTS_PROVIDERS` | `deepgram,openai` | Voices, tried in order; the next takes over when one fails |
| `BOSNIAN_TTS_VOICE` | `coral` | The OpenAI voice that speaks Bosnian |
| `ALLOWED_NUMBERS` | empty | Phone numbers that may call in or be called; empty admits no phone caller |
| `SIP_OUTBOUND_TRUNK_ID`, `RING_SECONDS` | unset, `30` | The trunk that dials out, and how long the phone may ring |
| `MAX_CALL_SECONDS`, `SILENCE_SECONDS` | `300`, `25` | Longest call, and how long a silent line is kept |
| `MAX_CONCURRENT_CALLS`, `DAILY_CALL_CAP` | `1`, `25` | Calls at once per worker, and per day |
| `DATABASE_URL` | unset | Also store calls in Postgres |
| `TRACE_ENDPOINT`, `TRACE_FILE` | unset | Send traces (personal data removed) to a collector, or write them to a file |

## Repository layout

```
src/clinic_voice_agent/
  gateway.py        the rules: identity, capability, offers, propose and commit, audit
  flow.py           the conversation: identify the caller, then help with the appointment
  menu.py choice.py the language menu, decided in code, and reading a choice
  locales.py        the wording and spoken times in each language
  worker.py         one call: admission, limits, the session, the record
  consent.py        the independent yes-check        review.py   the post-call review
  outbound.py       placing a call, and every reason not to
  limits.py         allowlist.py   hearing.py   the guards that do not depend on the model
  tracing.py        timeline.py    traces without personal data, and a call's own timeline
  records.py        store.py       the record of a call: a JSON file, and Postgres
  calls.py          reads those records back for the page
  web/              the page server: tokens, call list, call detail, call my phone
web/                the page (React, TypeScript)
evals/              scenarios, simulated callers, graders, the review cases, the privacy audit
scripts/            preflight, scripted caller, latency, language and voice probes, phone line setup
tests/              unit, behaviour (real model), store (Postgres)
docs/               PLAN, VERIFICATION, architecture decision records, images
Dockerfile, compose.yaml
```

## Known limitations

- **Phone calls are single-owner and not reproducible by others** (see above).
- **Spanish is only proven with scripted audio callers**, not yet a person on a phone line; Dutch and Bosnian have been tried by a native speaker. The wording in the other languages has had only partial review, and the menu takes about 15 seconds before the name is asked ([ADR-0011](docs/adr/0011-languages-in-a-call.md)).
- **About two seconds to reply.** Nearly every turn runs the model twice, once to pick the tool and once to word the answer. Two tools speak their own line to skip the second call.
- **No answering-machine detection.** Only the owner's own number is dialled, so a voicemail is theirs, but Emily would still speak to it.
- **At the concurrency cap the next caller waits in silence** until a call ends, rather than being told the line is busy.
- **Transcripts keep the date of birth the caller said**, in the records on disk and in Postgres. The audit log and the traces do not.
- **While the worker runs, the framework's own log lines name the phone call's room, which holds the caller's number.** Records, the database and traces use a hash or nothing instead.
- **The container clock is UTC**, which affects "tomorrow" in an appointment and the day boundary of the daily cap.
- **The deaf-transcriber guard** once ended a live call when it should not have (a word the transcriber could not make out, at the language menu); it is now off there. It has never been seen to catch a real failure, because one cannot be made on demand.
- **The measurements are small and written by the author:** the eval scenarios and the review cases are hand-made, and the latency is a handful of calls.
- **Not for public hosting.** There is no authentication on the page server beyond being reachable only from your machine, and every call spends credit.
- **Not built yet:** handing a call over to a person.

## Documents

[PLAN](docs/PLAN.md) has the phases and what is done. [VERIFICATION](docs/VERIFICATION.md) records what has been proven and what is assumed. The decisions are in [docs/adr](docs/adr): the use case, the architecture, how the agent is kept from doing the wrong thing, the page, containers, taking calls, the guards, calling out, speech by language, languages in a call, and speech to speech, and traces without personal data.

## License

No license is granted. The source is published so it can be read and reviewed; please do not copy, redistribute, or reuse it without permission. All rights reserved.
