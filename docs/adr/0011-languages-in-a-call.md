# ADR-0011: Languages in a call

Status: accepted, 2026-11-16. Builds on [ADR-0010](0010-speech-by-language.md). Rewritten the same day after the first live tries failed (see "What went wrong").

## Context

A caller can need English, Mexican Spanish, Dutch or Bosnian. The best speech services differ by language (ADR-0010), a phone caller cannot pick a language on a screen, and the rules in the gateway must work the same in all four.

## Decision

- **The language menu is its own first step, decided in code** (`menu.py`). It has no model. Its only outcomes are a language, or, after a silence, English; it never ends the call and never acts on words that are not a language's name.
- **Emily says who she is, then offers each other language in its own voice**, then waits. The lines cannot be interrupted, so none is cut off by an echo, a cough or the caller's "Hello?" at pickup. A phone caller is also told a key for each ("diga español o pulse el 1"); the keypad works at any moment, even during a line.
- **The answer is read in code** (`choice.py`): a word in the transcript that is, or is nearly, the name of a language (in that language, in English, or in the neighbours' spelling). "Alex Rivera" and "Hello?" match nothing; two languages in one reply match nothing.
- **The wait restarts while the caller speaks.** A caller answers a second after the menu ends and the words arrive a second or two after that, so a fixed window after the last line missed them. Now each start or end of speech gives a fresh four seconds, up to twelve in all. Speech that is not a language is heard, ignored and also gives a little longer.
- **No answer is English.** She asks "May I have your full name, please?" in English and goes on. Silence never hangs up.
- **The menu's transcriber is OpenAI's, told the four names** (`gpt-4o-transcribe` with a hint). It was measured against Deepgram's multilingual model on phone-quality audio (below).
- **The deaf-transcriber guard is off during the menu.** Its premise, that the transcriber should have understood what was said, does not hold for one foreign word.
- **After a choice, a `switch_language` handoff** (as before) builds the next step with that language's transcriber and voice, prompt, greetings and spoken times, and keeps the name. Both later steps keep a `switch_language` tool, so the language can still change mid-call by speech (that path goes through the model and has not been measured like the menu).
- **The menu lines' audio is made all at once** while the introduction plays, not one after another.
- **The wording lives in one module, `locales.py`**. The gateway words offers and read-backs in the call's language; the consent check sees the same question and reply the caller heard.
- **Every call record carries a timeline** (`timeline.py`): when the caller started and stopped speaking, what the menu heard and chose, when words came back or did not.
- Speech services differ per step, not per call. `update_options` only changes settings within one provider; changing provider (Deepgram to OpenAI for Bosnian) is a handoff.

## What went wrong, and why this shape

The first version let the model run the menu and let the lines queue. Three live calls showed:

1. The greeting was cut off by the callee's "Hello?", and the lines behind it played on regardless, because an interruption drops only the line playing.
2. "Bosanski" reached the model as "Both ones keep". The idea that Bosnian arrives garbled but usable came from clean synthetic sentences; one word on a phone line was a different case.
3. With no words back, nothing drove a reply, and every wordless sound counted towards the deaf-transcriber guard, which hung up and said "I can't hear you".
4. Each line's speech was made only when its turn came, which left gaps.

The common cause was building the menu out of parts made for conversation (a model deciding, a guard expecting understanding, interruptible lines) instead of a small decision made in code with a safe default.

## Measured (synthetic voices, phone-degraded)

`scripts/choice_probe.py`: each language's name alone and in a short phrase, spoken by three or four voices, degraded to 8 kHz, narrow band, mu-law with noise, then transcribed and read by `choice.py`.

| Transcriber | Clean line | Phone line | Dutch on phone | Bosnian on phone |
|---|---|---|---|---|
| Deepgram multilingual | 30/33 | 19/33 | 0/9 | 1/6 |
| Deepgram multilingual + the names as key terms | 32/33 | 19/33 | 0/9 | 1/6 |
| OpenAI, no hint | 31/33 | 21/33 | 2/9 | 1/6 |
| OpenAI, told the four names | 32/33 | 30/33 | 6/9 | 6/6 |

OpenAI with the hint is the best of four and still misses Dutch a third of the time on a degraded line, and sometimes answers a one-word clip with the hint itself. That is why the keypad exists. Real voices on a real line are the check that counts; these are not.

## Consequences

- The menu takes about 15 seconds of speech before the answer window opens, then the name question. That is long; shortening the introduction or the three lines is a decision about wording the owner has to make.
- Callers cannot talk over the lines. They can press a key, or answer in the pause.
- A browser caller has no keypad and is not told of one; they can speak.
- Lines the owner has not reviewed are marked as drafts by `scripts/print_locales.py`, now including the keypad cues.
- The daily-cap message stays English, because the language is unknown when it is said.
- Bosnian reply time is likely longer once chosen: OpenAI's transcriber does not stream.
- Times other than whole and half hours are refused by the language clocks. The mock clinic only produces those two.
