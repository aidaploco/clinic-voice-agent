"""Turning data into words a person would say on the phone."""

from datetime import datetime

_ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
         "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
         "eighteen", "nineteen"]  # fmt: skip
_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty"}


def say_clock(when: datetime) -> str:
    """ "four thirty in the afternoon", "nine in the morning", "noon".

    Written out in words on purpose. Given "4:30 PM" the voice put an audible gap between the
    hour and the minutes (measured: up to 430 ms of silence inside the time, against under 150 ms
    for the words), so the text that reaches it never contains a digit-and-colon time.
    """
    if when.minute == 0 and when.hour in (0, 12):
        return "midnight" if when.hour == 0 else "noon"
    hour = _ONES[when.hour % 12 or 12]
    if when.minute == 0:
        minutes = ""
    elif when.minute < 10:
        minutes = f" oh {_ONES[when.minute]}"
    elif when.minute < 20:
        minutes = f" {_ONES[when.minute]}"
    else:
        minutes = f" {_TENS[when.minute // 10]}" + (
            f" {_ONES[when.minute % 10]}" if when.minute % 10 else ""
        )
    if when.hour < 12:
        part = "in the morning"
    elif when.hour < 17:
        part = "in the afternoon"
    elif when.hour < 21:
        part = "in the evening"
    else:
        part = "at night"
    return f"{hour}{minutes} {part}"


def say_when(when: datetime, now: datetime) -> str:
    """ "tomorrow at three thirty in the afternoon", "Thursday at nine in the morning"."""
    days_away = (when.date() - now.date()).days
    if days_away == 0:
        day = "today"
    elif days_away == 1:
        day = "tomorrow"
    elif 1 < days_away < 7:
        day = when.strftime("%A")
    else:
        day = f"{when.strftime('%A')} the {_ordinal(when.day)}"
    return f"{day} at {say_clock(when)}"


def _ordinal(day: int) -> str:
    if 10 <= day % 100 <= 20:
        return f"{day}th"
    return f"{day}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th') }"
