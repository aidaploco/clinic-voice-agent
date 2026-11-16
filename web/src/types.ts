/** What the Python side sends. Shapes match `Gateway`'s audit events and the call record. */

export interface AuditEvent {
  at: string;
  operation: string;
  outcome: "allowed" | "refused";
  reason: string;
  details: Record<string, unknown>;
}

export type Verdict = "pass" | "fail" | "not_run";

export interface Check {
  name: string;
  verdict: Verdict;
  detail: string;
}

export interface CallRecord {
  ended_because: string;
  appointment_after: { start: string; status: string; practitioner: string } | null;
  checks: Check[];
}

export interface TokenResponse {
  url: string;
  token: string;
  room: string;
}

export interface Line {
  id: string;
  speaker: "caller" | "emily";
  text: string;
  final: boolean;
}
