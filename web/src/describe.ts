import type { AuditEvent, Check } from "./types";

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
