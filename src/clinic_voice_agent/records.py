"""The record of one call: what was said, and what the tools did."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from clinic_voice_agent.flow import CallState


def transcript_of(history) -> list[dict[str, str]]:
    """The spoken conversation from a session's chat history, in order."""
    lines = []
    for item in history.items:
        role = getattr(item, "role", None)
        text = getattr(item, "text_content", None)
        if role in ("user", "assistant") and text:
            lines.append({"speaker": "caller" if role == "user" else "agent", "text": text})
    return lines


def call_record(
    room: str,
    started: datetime,
    state: CallState,
    history,
    latency: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    patient = state.patient
    appointment = state.clinic.upcoming_appointment(patient.id) if patient else None
    return {
        "room": room,
        "started": started.isoformat(timespec="seconds"),
        "ended": datetime.now().isoformat(timespec="seconds"),
        "patient": patient.full_name if patient else None,
        "actions": state.actions,
        "appointment_after": None
        if appointment is None
        else {
            "start": appointment.start.isoformat(timespec="minutes"),
            "practitioner": appointment.practitioner,
            "status": appointment.status,
        },
        "messages": [m.text for m in state.clinic.messages],
        "latency_seconds": latency or {},
        "transcript": transcript_of(history),
    }


def save(record: dict[str, Any], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record['started'].replace(':', '')}-{record['room']}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return path
