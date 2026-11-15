"""Calls in Postgres. Needs a database to write to, so it is skipped without one.

    docker compose up -d db
    docker compose exec db createdb -U clinic clinic_test
    TEST_DATABASE_URL=postgresql://clinic:clinic-local-only@127.0.0.1:54329/clinic_test \\
        uv run pytest tests/store
"""

import os

import psycopg
import pytest
from psycopg import sql

from clinic_voice_agent import store

URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(not URL, reason="needs TEST_DATABASE_URL")

RECORD = {
    "room": "room-1",
    "started": "2026-11-16T10:00:00",
    "ended": "2026-11-16T10:02:30",
    "ended_because": "agent_ended_call",
    "errors": [],
    "patient_id": "patient-alex",
    "appointment_after": {"start": "2026-11-19T16:30", "status": "confirmed"},
    "latency_seconds": {"reply": {"median": 1.6}},
    "transcript": [
        {"speaker": "agent", "text": "May I have your full name?"},
        {"speaker": "caller", "text": "Alex Rivera."},
    ],
    "audit": [
        {
            "at": "2026-11-16T10:00:20",
            "operation": "identity_check",
            "outcome": "allowed",
            "reason": "",
            "details": {"patient_id": "patient-alex", "attempt": 1},
        },
        {
            "at": "2026-11-16T10:01:40",
            "operation": "commit_change",
            "outcome": "allowed",
            "reason": "",
            "details": {"proposal": "p1", "confirmation": {"read_back": "Move…", "said": "Yes."}},
        },
    ],
    "checks": [{"name": "changes_were_confirmed", "verdict": "pass", "detail": ""}],
}


@pytest.fixture(scope="module", autouse=True)
def tables():
    store.migrate(URL)


def count(table: str, call_id=None) -> int:
    query = sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
    with psycopg.connect(URL) as conn:
        if call_id is None:
            return conn.execute(query).fetchone()[0]
        return conn.execute(query + sql.SQL(" WHERE call_id = %s"), (call_id,)).fetchone()[0]


def test_migrating_twice_applies_nothing_the_second_time():
    assert store.migrate(URL) == []


async def test_a_call_is_stored_with_its_transcript_audit_log_and_review():
    call_id = await store.save_call(URL, RECORD)
    assert count("transcript_lines", call_id) == 2
    assert count("audit_events", call_id) == 2
    assert count("call_checks", call_id) == 1
    with psycopg.connect(URL) as conn:
        said = conn.execute(
            "SELECT details -> 'confirmation' ->> 'said' FROM audit_events "
            "WHERE call_id = %s AND operation = 'commit_change'",
            (call_id,),
        ).fetchone()[0]
        patient, ended = conn.execute(
            "SELECT patient_id, ended_at - started_at FROM calls WHERE id = %s", (call_id,)
        ).fetchone()
    assert said == "Yes."
    assert patient == "patient-alex" and ended.total_seconds() == 150


async def test_a_record_that_cannot_be_stored_whole_is_not_stored_at_all():
    before = count("calls"), count("transcript_lines")
    broken = RECORD | {"checks": [{"name": "x", "verdict": "not a verdict", "detail": ""}]}
    with pytest.raises(psycopg.errors.CheckViolation):
        await store.save_call(URL, broken)
    assert (count("calls"), count("transcript_lines")) == before
