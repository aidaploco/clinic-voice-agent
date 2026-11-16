# ADR-0010: Which speech services for which language

Status: proposed, 2026-11-16. Measured on synthetic speech; Bosnian is not decided (see "Open").

## Context

Phase 5 adds Mexican Spanish, Dutch and Bosnian to English. The plan called Bosnian the known risk: the speech-to-text plugin's own language list does not mention it. That was about the plugin's documentation. Deepgram's model list says its `nova-3` handles Bosnian (`bs`, `bs-BA`), with streaming, and the plugin accepts any language string. The plan also says the table of services per language is "decided by measurement", so this was measured.

## Method

`scripts/language_probe.py`: the receptionist's eight sentences in each language (`evals/languages.yaml`) are spoken by a voice, transcribed by a transcriber, and scored against the text (word error rate, 0.00 is perfect). Every voice is paired with every transcriber, so a poor score can be traced to its side. Five sentences per language are scored on their words; the three that carry numbers are shown as heard, because "nine" and 9, or "half elf" and 10:30, are all right and cannot be told from errors automatically. Serbian Cyrillic is compared as Latin, since a transcriber may answer Bosnian in either script. The Mac's Croatian voice stands in as a second, independent Bosnian voice; it is a measuring aid and not something the product could ship.

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
| Bosnian | OpenAI | 0.16 | 0.08 |
| Bosnian | Mac, Croatian | 0.11 | 0.05 |

- **English, Spanish, Dutch:** both transcribers and both voices are good. Deepgram has native voices for all three (six Mexican Spanish voices, nine Dutch), and its transcriber streams, which phone calls need.
- **Bosnian transcription is the open question.** OpenAI's is more accurate and heard the numbers right, but wrote Cyrillic for some sentences (names and short ones) and Latin for others. Deepgram's stays in Latin script but dropped parts of the long, number-heavy sentences with both voices: "srijedu u četiri i trideset" in one, "utorak u deset i" in another. Those are the offer and read-back sentences.
- **Bosnian speech has one candidate, OpenAI's voice.** Deepgram has no Bosnian, Croatian or Serbian voice. How it sounds, and whether the Mac's Croatian voice is a fair stand-in, needs a native ear.

## Decision

For English, Spanish and Dutch: Deepgram `nova-3` to hear and Aura-2 to speak (Mexican voices for Spanish), with OpenAI as the voice fallback already in place.

For Bosnian: not decided yet.

## Open

- **Bosnian transcriber.** Deepgram (streams, Latin script, drops number-heavy chunks) or OpenAI (more accurate, mixed script, not a streaming service in the plugin, so slower). A native speaker's own voice on a phone line is the test that matters; this one used clean synthetic audio.
- **Bosnian voice.** OpenAI's is the only one available now; Azure and Google have Bosnian or Serbian voices but need an account.
- **The Spanish, Dutch and Bosnian sentences are drafts** that a native speaker has not yet reviewed.
- Names and a Cyrillic answer need handling whichever transcriber is used: the clinic's name matching must read Cyrillic.

## Consequences

- This ranks services on clean synthetic speech. A real caller on a phone line, with an accent, is harder, so the numbers are a floor and not a forecast.
- Five scored sentences per combination is a small sample; a difference of 0.03 is noise.
