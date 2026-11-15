-- One row per call, and what happened in it.

CREATE TABLE calls (
    id                uuid PRIMARY KEY,
    room              text        NOT NULL,
    started_at        timestamptz NOT NULL,
    ended_at          timestamptz NOT NULL,
    ended_because     text        NOT NULL,
    patient_id        text,
    appointment_after jsonb,
    latency_seconds   jsonb       NOT NULL DEFAULT '{}',
    errors            jsonb       NOT NULL DEFAULT '[]'
);

CREATE INDEX calls_started_at ON calls (started_at DESC);

-- What was said, in order.
CREATE TABLE transcript_lines (
    call_id  uuid NOT NULL REFERENCES calls (id) ON DELETE CASCADE,
    position int  NOT NULL,
    speaker  text NOT NULL CHECK (speaker IN ('caller', 'agent')),
    text     text NOT NULL,
    PRIMARY KEY (call_id, position)
);

-- Every request the gateway saw, allowed or refused, in order.
CREATE TABLE audit_events (
    call_id   uuid        NOT NULL REFERENCES calls (id) ON DELETE CASCADE,
    position  int         NOT NULL,
    at        timestamptz NOT NULL,
    operation text        NOT NULL,
    outcome   text        NOT NULL CHECK (outcome IN ('allowed', 'refused')),
    reason    text        NOT NULL DEFAULT '',
    details   jsonb       NOT NULL DEFAULT '{}',
    PRIMARY KEY (call_id, position)
);

CREATE INDEX audit_events_operation ON audit_events (operation, outcome);

-- The post-call review: does what was done match what was said?
CREATE TABLE call_checks (
    call_id uuid NOT NULL REFERENCES calls (id) ON DELETE CASCADE,
    name    text NOT NULL,
    verdict text NOT NULL CHECK (verdict IN ('pass', 'fail', 'not_run')),
    detail  text NOT NULL DEFAULT '',
    PRIMARY KEY (call_id, name)
);
