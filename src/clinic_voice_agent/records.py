"""The record of one call: what was said, what the gateway allowed and refused, and the review."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from clinic_voice_agent.clinic import Clinic
from clinic_voice_agent.gateway import Gateway


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
    gateway: Gateway,
    clinic: Clinic,
    transcript: list[dict[str, str]],
    latency: dict[str, dict[str, float]] | None = None,
    ended_because: str = "",
    errors: list[dict[str, Any]] | None = None,
    checks: list[dict[str, str]] | None = None,
    direction: str | None = None,
    timeline: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    patient = gateway.patient
    appointment = clinic.last_known_appointment(patient.id) if patient else None
    return {
        "room": room,
        "direction": direction,  # "outbound" for a call Emily placed, otherwise None
        # With a UTC offset, so the time means the same wherever it is read: a record written in
        # a container (UTC) and read on a laptop must not shift by hours.
        "started": started.astimezone().isoformat(timespec="seconds"),
        "ended": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ended_because": ended_because,
        "errors": errors or [],
        "patient_id": patient.id if patient else None,
        "audit": [event.as_dict() for event in gateway.audit],
        "checks": checks or [],
        "appointment_after": None
        if appointment is None
        else {
            "start": appointment.start.isoformat(timespec="minutes"),
            "practitioner": appointment.practitioner,
            "status": appointment.status,
        },
        "messages": [m.text for m in clinic.messages],
        "latency_seconds": latency or {},
        "timeline": timeline or [],
        "transcript": transcript,
    }


def save(record: dict[str, Any], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = record["started"][:19].replace(":", "")  # without the offset: it is the file's name
    path = directory / f"{stamp}-{record['room']}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return path
