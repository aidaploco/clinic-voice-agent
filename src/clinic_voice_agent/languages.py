"""The languages the receptionist speaks.

Each language is a row of data, not a branch in the code. Adding one means
adding a row here and passing that language's evals. Which speech services can
handle each one is decided, with measurements, in the languages phase
(docs/PLAN.md); until then only English is wired to speech.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str  # ISO 639-1
    locale: str  # the regional variety the clinic's callers speak
    english_name: str
    native_name: str


LANGUAGES: dict[str, Language] = {
    language.code: language
    for language in (
        Language("en", "en-US", "English", "English"),
        Language("es", "es-MX", "Spanish (Mexico)", "Español (México)"),
        Language("nl", "nl-NL", "Dutch", "Nederlands"),
        Language("bs", "bs-BA", "Bosnian", "Bosanski"),
    )
}

DEFAULT_LANGUAGE = LANGUAGES["en"]


def language_for(code: str) -> Language:
    """The supported language for a code such as "es", "es-MX" or "ES"; English if unknown.

    A caller whose language is not supported still gets a working call, in
    English, instead of an error.
    """
    return LANGUAGES.get(code.strip().lower().split("-")[0], DEFAULT_LANGUAGE)
