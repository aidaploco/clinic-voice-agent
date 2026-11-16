import type { AuditEvent, CallSummary, Channel, Check } from "./types";

const EVENT_TITLES: Record<string, string> = {
  identity_check: "Checked who is calling",
  offer_slots: "Looked up free times",
  propose_change: "Proposed a change (nothing changed yet)",
  commit_change: "Committed the change",
  take_message: "Took a message for the clinic",
};

const CHECK_TITLES: Record<string, string> = {
  changes_follow_identity: "Nothing was changed before the caller was verified",
  changes_were_confirmed: "Every change followed a clear yes",
  said_matches_done: "What she told the caller matches what was done",
};

const words = (reason: string) => reason.replaceAll("_", " ");

export function describeEvent(event: AuditEvent): { title: string; detail: string } {
  const title = EVENT_TITLES[event.operation] ?? event.operation;
  const d = event.details;
  if (event.outcome === "refused") {
    return { title, detail: `Refused: ${words(event.reason || "not allowed")}` };
  }
  switch (event.operation) {
    case "identity_check":
      return { title, detail: `Attempt ${String(d.attempt ?? "?")}: name and date of birth matched` };
    case "offer_slots": {
      const offers = Array.isArray(d.offers) ? d.offers.length : 0;
      return { title, detail: `${offers} times offered, under ids made up for this call` };
    }
    case "propose_change":
      return { title, detail: `Asked: ${String(d.read_back ?? "")}` };
    case "commit_change": {
      const said = (d.confirmation as { said?: unknown } | undefined)?.said;
      return { title, detail: `She said: “${String(said ?? "")}”` };
    }
    default:
      return { title, detail: "" };
  }
}

export const checkTitle = (check: Check) => CHECK_TITLES[check.name] ?? check.name;

/** One honest sentence about the checks: a check that could not run is not a pass. */
export function summariseChecks(checks: Check[]): string {
  const count = (verdict: string) => checks.filter((c) => c.verdict === verdict).length;
  const failed = count("fail");
  const skipped = count("not_run");
  if (failed) return `${failed} of ${checks.length} checks need a person to read them.`;
  if (skipped) return `${count("pass")} of ${checks.length} checks passed; ${skipped} could not run.`;
  return `All ${checks.length} checks passed.`;
}

export const agentStateLabel = (state: string): string =>
  ({
    idle: "Not on a call",
    disconnected: "Not on a call",
    connecting: "Connecting",
    initializing: "Connecting",
    listening: "Listening",
    thinking: "Thinking",
    speaking: "Speaking",
  })[state] ?? state;

const CHANNEL_LABELS: Record<Channel, string> = {
  phone: "Phone",
  browser: "Browser",
  test: "Scripted test",
  console: "Terminal",
  other: "Other",
};
export const channelLabel = (channel: Channel) => CHANNEL_LABELS[channel];

const ENDINGS: Record<string, string> = {
  caller_hung_up: "Caller hung up",
  agent_ended_call: "Emily ended the call",
  time_limit: "Time limit reached",
  silence: "Line went silent",
  stt_silent: "Could not hear the caller",
  worker_shutdown: "Worker stopped",
};
export function describeEnding(reason: string): string {
  if (reason.startsWith("service_failed")) return "A service failed";
  return ENDINGS[reason] ?? (reason ? reason.replaceAll("_", " ") : "Unknown");
}

const clock = (d: Date) => d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });

/** "Today, 8:54 PM", "Yesterday, 9:02 AM" or "Nov 14, 8:54 PM". */
export function describeStarted(iso: string, now: Date = new Date()): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "Unknown time";
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((day(now) - day(at)) / 86_400_000);
  if (days === 0) return `Today, ${clock(at)}`;
  if (days === 1) return `Yesterday, ${clock(at)}`;
  return `${at.toLocaleDateString("en-US", { month: "short", day: "numeric" })}, ${clock(at)}`;
}

/** What became of the appointment: "confirmed, Fri 9:00 AM" or that nobody was verified. */
export function describeOutcome(call: Pick<CallSummary, "appointment_after">): string {
  const after = call.appointment_after;
  if (!after) return "No patient verified";
  const when = new Date(after.start);
  const text = Number.isNaN(when.getTime())
    ? after.start
    : `${when.toLocaleDateString("en-US", { weekday: "short" })} ${clock(when)}`;
  return `${after.status}, ${text}`;
}

/** The review as one chip: a failure first, a skipped check never as a pass. */
export function reviewChip(checks: CallSummary["checks"]): { label: string; kind: "pass" | "fail" | "not_run" } {
  const total = checks.pass + checks.fail + checks.not_run;
  if (total === 0) return { label: "No review", kind: "not_run" };
  if (checks.fail) return { label: `${checks.fail} to read`, kind: "fail" };
  if (checks.not_run) return { label: `${checks.pass} of ${total} passed`, kind: "not_run" };
  return { label: "All passed", kind: "pass" };
}
