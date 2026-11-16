"""Telling a transcriber's echo of its own hint from something the caller said.

Some transcribers are given a short text as context (the language, the names to expect, an example
of how a date is said). On silence or noise they sometimes answer with that text. Heard as a
caller's turn it is worse than nothing: in a real call "Razgovor na bosanskom jeziku." was taken
for something the caller said, and the receptionist went on from it. A turn that is only a piece
of a hint is dropped.

Plain logic, tested without audio.
"""

import unicodedata

MENU_HINT = "The caller chooses a language: English, español, Nederlands or bosanski."
BOSNIAN_HINT = (
    "Razgovor na bosanskom jeziku, latinicom. Datum rođenja, na primjer: "
    "dvadeseti juni hiljadu devetsto osamdeset pete."
)
HINTS = (MENU_HINT, BOSNIAN_HINT)

# A turn this short that is part of a hint could be a caller's own words ("Nederlands"); only
# a stretch of several words that is also in a hint is taken for an echo.
LONGEST_REAL_MATCH = 2


def _words(text: str) -> list[str]:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    kept = "".join(c if c.isalnum() else " " for c in decomposed if not unicodedata.combining(c))
    return kept.split()


def is_echo(transcript: str) -> bool:
    """True if the transcript is a run of three or more words taken from one of the hints."""
    said = _words(transcript)
    if len(said) <= LONGEST_REAL_MATCH:
        return False
    joined = " " + " ".join(said) + " "
    return any(joined in " " + " ".join(_words(hint)) + " " for hint in HINTS)
