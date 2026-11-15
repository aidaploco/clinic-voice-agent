"""Turning data into words a person would say on the phone."""

from datetime import datetime


def say_when(when: datetime, now: datetime) -> str:
    """ "tomorrow at 3:30 PM", "Thursday at 9 AM", "Monday the 30th at 2 PM"."""
    hour = when.hour % 12 or 12
    clock = f"{hour}:{when.minute:02d}" if when.minute else f"{hour}"
    clock += " AM" if when.hour < 12 else " PM"
    days_away = (when.date() - now.date()).days
    if days_away == 0:
        day = "today"
    elif days_away == 1:
        day = "tomorrow"
    elif 1 < days_away < 7:
        day = when.strftime("%A")
    else:
        day = f"{when.strftime('%A')} the {_ordinal(when.day)}"
    return f"{day} at {clock}"


def _ordinal(day: int) -> str:
    if 10 <= day % 100 <= 20:
        return f"{day}th"
    return f"{day}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th') }"
