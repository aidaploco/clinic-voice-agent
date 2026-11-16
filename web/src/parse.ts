import type { AuditEvent, CallRecord, CallSummary, Channel, Check, Line, TokenResponse, Verdict } from "./types";

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const VERDICTS: readonly string[] = ["pass", "fail", "not_run"];

function toAuditEvent(value: unknown): AuditEvent | null {
  if (!isObject(value) || typeof value.operation !== "string") return null;
  if (value.outcome !== "allowed" && value.outcome !== "refused") return null;
  return {
    at: typeof value.at === "string" ? value.at : "",
    operation: value.operation,
    outcome: value.outcome,
    reason: typeof value.reason === "string" ? value.reason : "",
    details: isObject(value.details) ? value.details : {},
  };
}

/** A gateway event from the room, or null if what arrived is not one. Never throws. */
export function parseAuditEvent(text: string): AuditEvent | null {
  try {
    return toAuditEvent(JSON.parse(text));
  } catch {
    return null;
  }
}

export function parseToken(value: unknown): TokenResponse {
  if (
    !isObject(value) ||
    typeof value.url !== "string" ||
    typeof value.token !== "string" ||
    typeof value.room !== "string"
  ) {
    throw new Error("the server did not return a call token");
  }
  return { url: value.url, token: value.token, room: value.room };
}

export function parseRecord(value: unknown): CallRecord {
  if (!isObject(value)) throw new Error("not a call record");
  const checks: Check[] = Array.isArray(value.checks)
    ? value.checks.filter(isObject).map((c) => ({
        name: String(c.name ?? ""),
        verdict: (VERDICTS.includes(String(c.verdict)) ? c.verdict : "not_run") as Verdict,
        detail: String(c.detail ?? ""),
      }))
    : [];
  const after = isObject(value.appointment_after) ? value.appointment_after : null;
  const transcript: Line[] = Array.isArray(value.transcript)
    ? value.transcript.filter(isObject).map((line, i) => ({
        id: `past-${i}`,
        speaker: line.speaker === "caller" ? ("caller" as const) : ("emily" as const),
        text: String(line.text ?? ""),
        final: true,
      }))
    : [];
  const audit: AuditEvent[] = Array.isArray(value.audit)
    ? value.audit.map(toAuditEvent).filter((e): e is AuditEvent => e !== null)
    : [];
  return {
    started: String(value.started ?? ""),
    transcript,
    audit,
    ended_because: String(value.ended_because ?? ""),
    appointment_after: after
      ? {
          start: String(after.start ?? ""),
          status: String(after.status ?? ""),
          practitioner: String(after.practitioner ?? ""),
        }
      : null,
    checks,
  };
}

const CHANNELS: readonly string[] = ["phone", "browser", "test", "console", "other"];

/** The rows of the call list. A row that is not well formed is dropped, not guessed at. */
export function parseSummaries(value: unknown): CallSummary[] {
  if (!isObject(value) || !Array.isArray(value.calls)) return [];
  const rows: CallSummary[] = [];
  for (const row of value.calls) {
    if (!isObject(row) || typeof row.id !== "string" || !row.id) continue;
    const checks = isObject(row.checks) ? row.checks : {};
    const after = isObject(row.appointment_after) ? row.appointment_after : null;
    rows.push({
      id: row.id,
      channel: (CHANNELS.includes(String(row.channel)) ? row.channel : "other") as Channel,
      started: String(row.started ?? ""),
      ended_because: String(row.ended_because ?? ""),
      appointment_after: after
        ? {
            start: String(after.start ?? ""),
            status: String(after.status ?? ""),
            practitioner: String(after.practitioner ?? ""),
          }
        : null,
      checks: {
        pass: Number(checks.pass) || 0,
        fail: Number(checks.fail) || 0,
        not_run: Number(checks.not_run) || 0,
      },
      turns: Number(row.turns) || 0,
      changed: row.changed === true,
    });
  }
  return rows;
}
