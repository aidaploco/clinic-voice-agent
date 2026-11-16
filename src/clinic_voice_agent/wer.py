"""How far a transcript is from what was said: the word error rate.

Used to compare speech services by round trip: text is spoken by one service, transcribed
by another, and the transcript is scored against the text. Words are compared after a plain
normalisation (case, punctuation and spacing), so "Dr. Okafor," and "dr okafor" are the same.
Accents are kept: in Spanish and Bosnian a missing accent is a different word.
"""

import re
import unicodedata

_NOT_A_WORD = re.compile(r"[^\w\s]|_", re.UNICODE)

# Serbian Cyrillic to the Latin letters Bosnian is written in. A transcriber may answer in either
# script for the same speech. That is a choice of script, not a mistake, so both are compared
# in Latin.
_CYRILLIC = dict(
    zip(
        "абвгдђежзијклљмнњопрстћуфхцчџш",
        ["a", "b", "v", "g", "d", "đ", "e", "ž", "z", "i", "j", "k", "l", "lj", "m", "n", "nj",
         "o", "p", "r", "s", "t", "ć", "u", "f", "h", "c", "č", "dž", "š"],
        strict=True,
    )
)  # fmt: skip


def words(text: str) -> list[str]:
    """The words of a text, lower-cased, without punctuation. Numbers stay as written."""
    text = unicodedata.normalize("NFC", text).casefold().replace("'", "").replace("’", "")
    text = "".join(_CYRILLIC.get(ch, ch) for ch in text)
    return _NOT_A_WORD.sub(" ", text).split()


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Substitutions, insertions and deletions needed to turn the hypothesis into the reference,
    over the number of words in the reference. 0.0 is perfect; above 1.0 is possible."""
    ref, hyp = words(reference), words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i]
        for j, hyp_word in enumerate(hyp, start=1):
            cost = 0 if ref_word == hyp_word else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1] / len(ref)
