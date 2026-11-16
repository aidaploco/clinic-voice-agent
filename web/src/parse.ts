import type { AuditEvent, CallRecord, Check, TokenResponse, Verdict } from "./types";

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const VERDICTS: readonly string[] = ["pass", "fail", "not_run"];

/** A gateway event from the room, or null if what arrived is not one. Never throws. */
export function parseAuditEvent(text: string): AuditEvent | null {
  try {
    const value: unknown = JSON.parse(text);
    if (!isObject(value) || typeof value.operation !== "string") return null;
    if (value.outcome !== "allowed" && value.outcome !== "refused") return null;
    return {
      at: typeof value.at === "string" ? value.at : "",
      operation: value.operation,
      outcome: value.outcome,
      reason: typeof value.reason === "string" ? value.reason : "",
      details: isObject(value.details) ? value.details : {},
    };
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
  return {
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
