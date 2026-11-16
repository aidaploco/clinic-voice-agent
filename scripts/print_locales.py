"""Print every line the receptionist says from code, in every language, for a person to read.

    uv run python scripts/print_locales.py            # all four
    uv run python scripts/print_locales.py bs         # one

Lines marked (draft) were written by analogy and have not been reviewed by a native speaker; the
others are the sentences in evals/languages.yaml, which have.
"""

import sys
from datetime import datetime, timedelta

from clinic_voice_agent.locales import LOCALES, Locale

NOW = datetime(2026, 11, 16, 10, 0)  # a Monday
OKAFOR, LINDQVIST = "Dr. Okafor", "Dr. Lindqvist"
TREATMENT = "shoulder physiotherapy"


def at(days: int, hour: int, minute: int = 0) -> datetime:
    return (NOW + timedelta(days=days)).replace(hour=hour, minute=minute)


def rows(lc: Locale) -> list[tuple[str, str, bool]]:
    """(what it is, what is said, whether it is a draft)."""
    slots = [(at(2, 10, 30), OKAFOR), (at(3, 16, 30), OKAFOR), (at(4, 9), LINDQVIST)]
    offers = [(lc.when(when, NOW, "at"), who) for when, who in slots]
    same_doctor = [(said, OKAFOR) for said, _ in offers]
    was = (at(1, 15, 30), OKAFOR)

    def move(doctor: str) -> str:
        return lc.move_sentence(TREATMENT, was, (at(4, 9), doctor), NOW)

    def simple(template: str) -> str:
        return template.format(
            treatment=lc.treatment(TREATMENT),
            practitioner=lc.practitioner(OKAFOR),
            at=lc.when(was[0], NOW, "at"),
        )

    return [
        ("greeting, inbound", lc.greeting, False),
        ("greeting, outbound", lc.outbound_greeting, True),
        (
            "menu line, spoken in its own voice",
            (lc.menu_line(False) + "  |  on a phone: " + lc.menu_line(True))
            if lc.menu
            else "(none: English is the greeting)",
            True,
        ),
        ("after switching: asks for the name", lc.ask_name, True),
        ("after switching: asks for the date of birth", lc.ask_dob, False),
        ("offer, same doctor", lc.offer_sentence(same_doctor), False),
        ("offer, different doctors", lc.offer_sentence(offers), True),
        ("move read-back, same doctor", move(OKAFOR), False),
        ("move read-back, other doctor", move(LINDQVIST), True),
        ("cancel read-back", simple(lc.cancel), True),
        ("confirm read-back", simple(lc.confirm), True),
        ("goodbye: time limit", lc.time_limit_goodbye, True),
        ("goodbye: silence", lc.silence_goodbye, True),
        ("goodbye: cannot hear", lc.deaf_goodbye, False),
    ]


def show(code: str) -> None:
    lc = LOCALES[code]
    print(f"\n==================== {lc.llm_language} ({code})")
    for label, text, draft in rows(lc):
        print(f"\n  {label}{' (draft)' if draft else ''}\n    {text}")


if __name__ == "__main__":
    for code in sys.argv[1:] or list(LOCALES):
        show(code)
