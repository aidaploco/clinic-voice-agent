# ADR-0012: One speech-to-speech model instead of three services

Status: decided, 2026-11-16. Recommendation: keep the three-service chain. The comparison was cut short on the owner's judgement, so the numbers below are small.

## Question

The chain (a transcriber, a text model, a voice) adds a hand-off at each step. A speech-to-speech model hears and speaks directly. Would it be faster, cheaper or better to listen to, with the same receptionist, tools and gateway?

## What was built

`PIPELINE=realtime` runs the same flow on OpenAI's `gpt-realtime` (the plugin has a second family, `gpt-live-1`, billed per minute with tools run on a backend model; it was not used). `REALTIME_WAITS=true` adds a bounded wait for the caller's transcript before a commit. The default is, and stays, the chain. `evals/compare_pipelines.py` runs the same scripted audio calls through each arm in turn, alternating, and grades them with the evals' own grader. Both arms start at the identity step, in English, with the language menu off.

Three things had to change to carry the gateway design over, and they are the real findings:

1. **No `say`.** The model has no text-to-speech, so `session.say` raises. Every fixed line (greeting, offers, the read-back) is instead handed to the model with "say this word for word". The read-back is the line the consent check depends on, so the record keeps every line she was owed, and what the yes-check was shown. In the runs made, every owed line was spoken exactly as written and the yes-check was shown the question the caller heard. That is an observation, not a guarantee: with the chain, code speaks the line.
2. **The caller's reply arrives late.** The model hears audio and can call `commit_change` before the caller's transcript has reached the session history. The gateway refuses (`no_answer_yet`), which is safe. In the two plain runs, that happened both times; in one the model then re-asked the question and the call failed to move the appointment. A bounded wait for the transcript (3 seconds, with the rule unchanged: the caller must have spoken since the read-back) avoided it in the one run made.
3. **The language menu is not carried over.** It is built on separate speech services per language.

## Measured (6 spoken scripted calls: 2 chain, 2 plain, 1 with the wait, in 2 runs of the same move scenario)

| | Chain | Speech to speech | Speech to speech with the wait |
|---|---|---|---|
| Reply time as the caller feels it, median (turns) | 2.1 s (10) | 2.1 s (12) | 1.7 s (5) |
| Slowest turn | 3.1 s | 3.7 s | 6.9 s |
| Cost per call (models in the call; not the yes-check or the review) | $0.034 | $0.131 | $0.117 |
| Calls that came out right | 2 of 2 | 1 of 2 | 1 of 1 |

Prices were read from OpenAI's and Deepgram's pages on 2026-11-16 (Deepgram's are shown as promotional). Reply time is the caller's own clock in `audio_caller.py`, with a macOS voice, English, on a clean line.

## The owner's listening

The owner tried the speech-to-speech arm herself, by voice, and said it did not sound any better than the chain and that she would go back.

## Recommendation

Keep the chain.

- It was not faster in these runs.
- It costs about four times as much per call.
- The safety-critical lines are spoken by code rather than asked of a model, and the commit does not depend on a transcript arriving before the model acts.
- It sounded no better to the person who matters here.
- The chain supports the four languages, the menu and the keypad; this arm does not.

What would change this: a speech-to-speech model that can speak text it is given verbatim (a `say`), makes the transcript available before it acts, and is clearly better in Bosnian. None of those was found.

## Not done

The 36-call comparison (6 scenarios, 2 to 3 rounds, three arms) that would have given sample sizes worth quoting; the Bosnian listening sample; a phone-line call on this arm; the language menu on it. The code stays, off by default, so the comparison can be rerun.
