# ADR-0010: Which speech services for which language

Status: accepted for English, Spanish and Dutch; for Bosnian, chosen on synthetic speech and pending a check with a real voice, 2026-11-16 (see "Open").

## Context

Phase 5 adds Mexican Spanish, Dutch and Bosnian to English. The plan called Bosnian the known risk: the speech-to-text plugin's own language list does not mention it. That was about the plugin's documentation. Deepgram's model list says its `nova-3` handles Bosnian (`bs`, `bs-BA`), with streaming, and the plugin accepts any language string. The plan also says the table of services per language is "decided by measurement", so this was measured.

## Method

`scripts/language_probe.py`: the receptionist's eight sentences in each language (`evals/languages.yaml`) are spoken by a voice, transcribed by a transcriber, and scored against the text (word error rate, 0.00 is perfect). Every voice is paired with every transcriber, so a poor score can be traced to its side. Five sentences per language are scored on their words; the three that carry numbers are shown as heard, because "nine" and 9, or "half elf" and 10:30, are all right and cannot be told from errors automatically. Serbian Cyrillic is compared as Latin, since a transcriber may answer Bosnian in either script. The Spanish, Dutch and Bosnian sentences were drafted by the assistant and reviewed by the owner, a native speaker of all three, with one correction: Bosnian says half hours as "pola" the next hour ("pola jedanaest" for 10:30), which is what the Bosnian sentences now say. The Mac's Croatian voice stands in as a second, independent Bosnian voice; it is a measuring aid and not something the product could ship.

## What was measured

Mean word error rate on the scored sentences:

| Language | Voice | Deepgram nova-3 | OpenAI gpt-4o-transcribe |
|---|---|---|---|
| English | Aura-2 | 0.00 | 0.02 |
| English | OpenAI | 0.02 | 0.03 |
| Spanish (Mexico) | Aura-2, a Mexican voice | 0.03 | 0.04 |
| Spanish | OpenAI | 0.01 | 0.00 |
| Dutch | Aura-2 | 0.02 | 0.02 |
| Dutch | OpenAI | 0.02 | 0.08 |
| Bosnian | OpenAI | 0.30 | 0.00 (with a Latin-script hint; 0.08 without) |
| Bosnian | Mac, Croatian | 0.11 | 0.02 (with the hint; 0.05 without) |

- **English, Spanish, Dutch:** both transcribers and both voices are good. Deepgram has native voices for all three (six Mexican Spanish voices, nine Dutch), and its transcriber streams, which phone calls need.
- **Bosnian transcription: OpenAI's, with a hint.** On the natural half-hour phrasing OpenAI's transcriber was essentially perfect: it heard "pola jedanaest" and "pola pet" and the date of birth ("rođen 14. marta 1990"). Left alone it answered some sentences in Serbian Cyrillic, including a garbled one for the date-of-birth sentence; told in a one-line hint to write Bosnian in Latin script, it did so in all 16 sentences (0 Cyrillic). Deepgram's `nova-3` stays in Latin script, but with both voices it kept losing the start of the long offer and read-back sentences ("5 poslijepodne, ili četvrtak…") and garbled the name sentence, 0.11 to 0.30.
- **Bosnian speech: OpenAI's voice.** Deepgram has no Bosnian, Croatian or Serbian voice. The owner listened and judged OpenAI's Bosnian voice "pretty good"; the Mac's Croatian voice sounded robotic, as expected, and was only ever a second voice to measure the transcribers against.

## Decision

- **English, Spanish and Dutch:** Deepgram `nova-3` to hear and Aura-2 to speak (Mexican voices for Spanish), with OpenAI as the voice fallback already in place.
- **Bosnian:** OpenAI `gpt-4o-transcribe` to hear, with the Latin-script hint, and OpenAI `gpt-4o-mini-tts` to speak. Deepgram is not used for Bosnian.
- So the services differ by language, and the language selects them: the speech-to-text and text-to-speech of a call are set per language. `update_options` changes settings only within one provider, so moving between providers is done by handing the call to a step with its own services ([ADR-0011](0011-languages-in-a-call.md)).

## Open

- **A real Bosnian voice on a phone line.** This was clean synthetic speech; a native speaker's own voice, through the phone, is the test that matters. If it holds, Bosnian is settled.
- **Streaming.** OpenAI's transcriber streams only in its realtime mode (`use_realtime`); otherwise the plugin waits for a pause and transcribes the whole utterance, which adds time. Which to use is decided by measuring reply time in Bosnian.
- **Spoken times differ by language.** The clinic writes times out in words; that has to follow each language: Spanish "diez y media", Dutch "half elf", Bosnian "pola jedanaest". English says "ten thirty". The English function is not enough.
- **Names and a Cyrillic answer.** Name matching should read Cyrillic as well as Latin, as a safety net, though the hint makes it rare.

## Consequences

- This ranks services on clean synthetic speech. A real caller on a phone line, with an accent, is harder, so the numbers are a floor and not a forecast.
- Five scored sentences per combination is a small sample; a difference of 0.03 is noise. The Bosnian gap between the two transcribers (0.00 to 0.02 against 0.11 to 0.30) is large enough not to be.
