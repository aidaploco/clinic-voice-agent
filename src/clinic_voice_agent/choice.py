"""Reading a language choice out of a transcript, in code.

At the start of a call the caller says which language they want. That is decided here, not by a
model: the answer is one of four, a model that is asked may answer something else, and a call
must never be ended or sent the wrong way because of what a transcriber made of one word.

Each language is known by a few words (its name in itself, in English, and in the others'
spelling). A transcript matches if one of its words is, or is nearly, one of those: a transcriber
that has heard "espanol" as "espanyol" still counts. Nothing matches by accident on a name:
"Alex Rivera" and "Hello?" match no language.

Plain logic, tested without audio.
"""

import unicodedata
from difflib import SequenceMatcher

NAMES: dict[str, tuple[str, ...]] = {
    "en": ("english", "ingles", "engels", "engleski", "engelsk"),
    "es": ("espanol", "spanish", "castellano", "spaans", "spanisch", "spanski", "spanjolski"),
    "nl": ("nederlands", "dutch", "holandes", "holandski", "hollands", "nederlandse"),
    "bs": ("bosanski", "bosnian", "bosnio", "bosnisch", "bosnisk", "bosanskom", "bosanskog"),
}

# How alike a heard word must be to a name. Names are long and unlike each other, so a word
# that close is the name; a looser value starts matching real words ("bosnia" is not a choice).
CLOSE_ENOUGH = 0.8
SHORTEST_WORD = 5


def _plain(text: str) -> str:
    """Lower case, no accents or punctuation: what a transcriber gives is not spelt consistently."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    kept = (c if c.isalnum() else " " for c in decomposed if not unicodedata.combining(c))
    return "".join(kept)


def chosen_language(transcript: str) -> str | None:
    """The language a transcript asks for, or None if it asks for none (or for two)."""
    found = set()
    for word in _plain(transcript).split():
        if len(word) < SHORTEST_WORD:
            continue
        # The nearest name to this word, so a word close to two names counts for the closer.
        score, code = max(
            (SequenceMatcher(None, word, name).ratio(), code)
            for code, names in NAMES.items()
            for name in names
        )
        if score >= CLOSE_ENOUGH:
            found.add(code)
    return found.pop() if len(found) == 1 else None


# The keys that choose a language on a phone. English is what she opens in, so it has none.
KEYS: dict[str, str] = {"1": "es", "2": "nl", "3": "bs"}


def key_for(code: str) -> str:
    """The key that chooses a language."""
    return next(key for key, language in KEYS.items() if language == code)
