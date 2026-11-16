"""A timestamped list of what happened in a call, kept in its record.

A call that went wrong should explain itself: when the caller started and stopped speaking,
when she did, when the transcriber came back with words or did not, what the menu heard. The
framework's own log lines say some of it and not in one place, and not with the room's name
removed. Plain data: seconds since the call began, a kind, and what is worth knowing about it.
"""

import time
from typing import Any


class Timeline:
    def __init__(self, clock: Any = time.monotonic) -> None:
        self._clock = clock
        self._start = clock()
        self.entries: list[dict[str, Any]] = []

    def add(self, kind: str, **detail: Any) -> None:
        entry: dict[str, Any] = {"t": round(self._clock() - self._start, 2), "kind": kind}
        entry.update({key: value for key, value in detail.items() if value is not None})
        self.entries.append(entry)
