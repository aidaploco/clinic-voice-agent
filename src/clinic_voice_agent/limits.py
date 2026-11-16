"""Limits on what a call can cost: how long one may last, and how many a day.

A tab left open, or a caller who never hangs up, must not run up a bill. These
are enforced in the worker, so every way into it (a browser page, later a phone)
inherits them.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

TIME_LIMIT_GOODBYE = "I'm sorry, we've reached the time limit for this call. Goodbye."
CAP_REACHED = (
    "Thank you for calling Quillbrook Physio. We can't take any more calls today. "
    "Please try again tomorrow. Goodbye."
)


def calls_today(folder: Path, now: datetime) -> int:
    """How many calls have a record today. A call is counted when it ends, not while it runs."""
    if not folder.is_dir():
        return 0
    return sum(1 for path in folder.glob(f"{now:%Y-%m-%d}T*.json"))


async def hang_up_after(
    seconds: float,
    say_goodbye: Callable[[], Awaitable[None]],
    hang_up: Callable[[], None],
) -> None:
    """Wait, then say goodbye and hang up. Cancel the task to stop it (the call ended sooner)."""
    await asyncio.sleep(seconds)
    try:
        await say_goodbye()
    finally:
        # Even if speaking fails, the line is closed: the limit is on cost, not on manners.
        hang_up()
