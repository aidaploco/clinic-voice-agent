"""Who may reach Emily by phone.

Caller ID can be spoofed, so this is a limit on cost and abuse, not a proof of who is calling:
identity still takes a name and a date of birth. It is the second of two gates. The first is
the allowed-numbers list on the LiveKit inbound trunk, which turns most callers away before a
room exists; this one runs in the worker and fails closed, so an unset list admits no phone
caller at all.
"""

import re
from dataclasses import dataclass

E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def normalise(number: str) -> str:
    """Spaces, dashes, dots and brackets removed: "+1 (415) 555-0123" -> "+14155550123"."""
    return re.sub(r"[\s\-.()]", "", number)


def parse_allowed(raw: str) -> frozenset[str]:
    """The numbers in a comma-separated list. A malformed entry is an error, never skipped.

    The message names the position, not the value: this is a phone number.
    """
    numbers = set()
    for position, entry in enumerate((e for e in raw.split(",") if e.strip()), start=1):
        number = normalise(entry)
        if not E164.match(number):
            raise ValueError(
                f"entry {position} of ALLOWED_NUMBERS is not an E.164 number "
                "(a + followed by 7 to 15 digits, country code first)"
            )
        numbers.add(number)
    return frozenset(numbers)


def mask(number: str | None) -> str:
    """Enough to recognise a call in a log, not enough to dial: the last three digits."""
    return f"+…{number[-3:]}" if number and len(number) > 3 else "unknown"


@dataclass(frozen=True)
class Admission:
    allowed: bool
    reason: str
    caller: str  # masked


def admit(is_phone: bool, caller_number: str | None, allowed: frozenset[str]) -> Admission:
    """Whether to take this call. A browser page is the owner's machine; a phone is checked."""
    if not is_phone:
        return Admission(True, "browser", "browser")
    number = normalise(caller_number) if caller_number else ""
    if not E164.match(number):
        return Admission(False, "no_caller_number", "unknown")
    if number not in allowed:
        return Admission(False, "number_not_allowed", mask(number))
    return Admission(True, "number_allowed", mask(number))


DIALLED_PREFIX = "phone-out-"  # the identity this project gives the participant it dials


def admit_dialled(
    is_phone: bool, identity: str, caller_number: str | None, allowed: frozenset[str]
) -> Admission:
    """Whether to take a call this project placed itself.

    The number was chosen from the allowlist before anything was dialled, and the participant
    carries the identity given at dialling, which no one else can obtain. The number is checked
    again whenever the network shows it, and a number that is shown and not allowed is refused.
    """
    if not is_phone or not identity.startswith(DIALLED_PREFIX):
        return Admission(False, "not_the_dialled_party", "unknown")
    number = normalise(caller_number) if caller_number else ""
    if E164.match(number) and number not in allowed:
        return Admission(False, "number_not_allowed", mask(number))
    return Admission(True, "dialled", mask(number) if number else "dialled")
