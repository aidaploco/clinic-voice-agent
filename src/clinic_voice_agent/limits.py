"""Limits on what a call can cost: how long one may last, and how many a day.

A tab left open, or a caller who never hangs up, must not run up a bill. These
are enforced in the worker, so every way into it (a browser page, later a phone)
inherits them.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

CAP_REACHED = (
    "Thank you for calling Quillbrook Physio. We can't take any more calls today. "
    "Please try again tomorrow. Goodbye."
)


def concurrency_load(active: int, maximum: int) -> float:
    """The worker's load as the framework reads it: 1.0 when every allowed call is running.

    Above its threshold (0.7 under `start`) a worker marks itself unavailable and is given no
    new calls, so at the cap the next caller is not answered rather than answered at a cost.
    """
    return active / maximum


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
