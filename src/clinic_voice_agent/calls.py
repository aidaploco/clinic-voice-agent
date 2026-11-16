"""Reading finished calls back: a list of them, and one in full.

Records are the JSON files the worker writes (`records.py`). This only reads them, so the browser
page can show earlier calls, including phone calls that never touched the page. Pure and
synchronous; the server runs it off the event loop.
"""

import json
import re
from pathlib import Path
from typing import Any

# A record's file name: its start time, then the call id (`web-…`, `phone-…`, `test-…`, `console`).
FILE_NAME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{6}-(?P<id>[A-Za-z0-9][A-Za-z0-9_-]{0,63})\.json")
# Always used with fullmatch: `$` would also accept a trailing newline.
CALL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def channel_of(call_id: str) -> str:
    """How the call came in, from its id: phone, browser, a scripted test, or the terminal."""
    for prefix, channel in (("phone-", "phone"), ("web-", "browser"), ("test-", "test")):
        if call_id.startswith(prefix):
            return channel
    return "console" if call_id == "console" else "other"


def summarise(record: dict[str, Any]) -> dict[str, Any]:
    """What a list needs about a call. No transcript: that is for opening one."""
    checks = record.get("checks") or []
    audit = record.get("audit") or []
    call_id = str(record.get("room", ""))
    return {
        "id": call_id,
        "channel": channel_of(call_id),
        "started": record.get("started", ""),
        "ended_because": record.get("ended_because", ""),
        "appointment_after": record.get("appointment_after"),
        "checks": {
            verdict: sum(1 for c in checks if c.get("verdict") == verdict)
            for verdict in ("pass", "fail", "not_run")
        },
        "turns": sum(
            1 for line in record.get("transcript") or [] if line.get("speaker") == "caller"
        ),
        "changed": any(
            e.get("operation") == "commit_change" and e.get("outcome") == "allowed" for e in audit
        ),
    }


def _read(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return None  # a half-written or foreign file is skipped, never an error for the page
    return value if isinstance(value, dict) else None


def list_calls(folder: Path, limit: int = 50) -> list[dict[str, Any]]:
    """The newest `limit` calls, newest first."""
    if not folder.is_dir():
        return []
    names = sorted((p for p in folder.glob("*.json") if FILE_NAME.fullmatch(p.name)), reverse=True)
    summaries = []
    for path in names:
        if (record := _read(path)) is not None:
            summaries.append(summarise(record))
            if len(summaries) == limit:
                break  # the limit counts calls, not files: unreadable ones are skipped over
    return summaries


def find_call(folder: Path, call_id: str) -> dict[str, Any] | None:
    """One call in full, or None. The id must be exactly the id in a record's file name."""
    if not CALL_ID.fullmatch(call_id) or not folder.is_dir():
        return None
    for path in sorted(folder.glob("*.json"), reverse=True):
        match = FILE_NAME.fullmatch(path.name)
        if match and match.group("id") == call_id:
            return _read(path)
    return None
