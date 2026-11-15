"""Calls in Postgres: the call, its transcript, the gateway's audit log, the review.

Optional. Without DATABASE_URL a call's record is only the JSON file written by
`clinic_voice_agent.records`. With it, the same record is also stored here, in
one transaction, so a call is either wholly present or absent.

    docker compose up -d db                               # a local Postgres
    uv run python -m clinic_voice_agent.store migrate     # create or update the tables
"""

import sys
import uuid
from datetime import datetime
from importlib import resources
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

# Any two workers starting at once take this lock in turn, so a migration runs once.
_MIGRATION_LOCK = 7_264_001


def migrate(database_url: str) -> list[str]:
    """Apply the migrations that have not been applied yet. Returns their names."""
    files = sorted(
        (f for f in resources.files("clinic_voice_agent.migrations").iterdir()),
        key=lambda f: f.name,
    )
    applied_now = []
    with psycopg.connect(database_url) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK,))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {row[0] for row in conn.execute("SELECT name FROM schema_migrations")}
        for file in files:
            if not file.name.endswith(".sql") or file.name in done:
                continue
            conn.execute(file.read_text())
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (file.name,))
            applied_now.append(file.name)
    return applied_now


def _when(text: str) -> datetime:
    """A record's local time, with its time zone, so Postgres stores the instant."""
    return datetime.fromisoformat(text).astimezone()


async def save_call(database_url: str, record: dict[str, Any]) -> uuid.UUID:
    """Store one call's record. All of it, or none of it."""
    call_id = uuid.uuid4()
    async with await psycopg.AsyncConnection.connect(database_url) as conn:
        async with conn.transaction(), conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO calls (id, room, started_at, ended_at, ended_because, patient_id, "
                "appointment_after, latency_seconds, errors) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    call_id,
                    record["room"],
                    _when(record["started"]),
                    _when(record["ended"]),
                    record["ended_because"],
                    record.get("patient_id"),
                    Jsonb(record.get("appointment_after")),
                    Jsonb(record.get("latency_seconds") or {}),
                    Jsonb(record.get("errors") or []),
                ),
            )
            if lines := record.get("transcript"):
                await cur.executemany(
                    "INSERT INTO transcript_lines (call_id, position, speaker, text) "
                    "VALUES (%s, %s, %s, %s)",
                    [(call_id, i, line["speaker"], line["text"]) for i, line in enumerate(lines)],
                )
            if events := record.get("audit"):
                await cur.executemany(
                    "INSERT INTO audit_events (call_id, position, at, operation, outcome, "
                    "reason, details) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    [
                        (
                            call_id,
                            i,
                            _when(event["at"]),
                            event["operation"],
                            event["outcome"],
                            event["reason"],
                            Jsonb(event["details"]),
                        )
                        for i, event in enumerate(events)
                    ],
                )
            if checks := record.get("checks"):
                await cur.executemany(
                    "INSERT INTO call_checks (call_id, name, verdict, detail) "
                    "VALUES (%s, %s, %s, %s)",
                    [(call_id, c["name"], c["verdict"], c["detail"]) for c in checks],
                )
    return call_id


if __name__ == "__main__":
    from clinic_voice_agent.settings import get_settings

    url = get_settings().database_url
    if sys.argv[1:] != ["migrate"] or url is None:
        sys.exit("usage: python -m clinic_voice_agent.store migrate   (needs DATABASE_URL)")
    names = migrate(url.get_secret_value())
    print("applied: " + ", ".join(names) if names else "nothing to apply")
