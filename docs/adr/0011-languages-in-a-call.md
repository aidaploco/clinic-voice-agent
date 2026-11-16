# ADR-0011: Languages in a call

Status: accepted, 2026-11-16. Builds on [ADR-0010](0010-speech-by-language.md).

## Context

A caller can need English, Mexican Spanish, Dutch or Bosnian. The best speech services differ by language (ADR-0010), a phone caller cannot pick a language on a screen, and the rules in the gateway must work the same in all four.

## Decision

- **Emily opens in English and then offers each other language in that language's own voice**, one line each ("Para continuar en español, diga español."). The caller answers by saying the language, or just starts speaking it. The order is: who is calling, the three language lines, and only then the first question (the name). A first draft asked for the name first and listed the languages after it, which made no sense on the phone.
- **The first step listens with a multilingual transcriber** (Deepgram `multi`), because the language is not yet known. Spanish and Dutch are heard well that way; Bosnian comes out garbled but not empty, so the model can still tell what was asked for and the deaf-transcriber guard does not fire. The cost for English was negligible in the experiment.
- **A `switch_language` tool hands the call to a new step** (the same pattern as the identity-to-appointment handoff) built with that language's transcriber and voice, its prompt, its greetings and its way of saying times. The step keeps the caller's name, so Emily does not ask again. Both steps have the tool, so the language can change mid-call.
- **The wording lives in one module, `locales.py`**: greetings, questions, read-backs, goodbyes and spoken times per language. English is unchanged. The gateway builds offers and read-backs from the call's language, and the consent check sees the same question and reply the caller heard. The rules in the gateway do not depend on language.
- **Speech services differ per step, not per call.** ADR-0010 said the plugins allow `update_options` during a call. That only works within one provider. Changing provider (Deepgram to OpenAI for Bosnian) uses per-agent `stt` and `tts`, which is what the handoff does.
- **Spanish and Dutch voices** fall back to an OpenAI voice if Deepgram fails. Bosnian has one voice (OpenAI).

## Consequences

- The menu costs about ten seconds of speech before the caller can talk. A keypad shortcut for phone callers is possible later; it is not built.
- Garbled Bosnian at the first step means choosing Bosnian relies on the model reading a bad transcript. A fuzzy keyword match could back it up if that proves unreliable.
- Lines the owner has not reviewed are marked as drafts by `scripts/print_locales.py`: the cancel and confirm read-backs, the menu lines, the outbound greeting and the time-limit and silence goodbyes.
- The daily-cap message stays English, because the language is unknown when it is said.
- Bosnian reply time is likely longer: OpenAI's transcriber does not stream.
- Times other than whole and half hours are refused by the language clocks. The mock clinic only produces those two.
