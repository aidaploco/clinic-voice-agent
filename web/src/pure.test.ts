import { waitForRecord } from "./api";
import { agentStateLabel, checkTitle, describeEvent, summariseChecks } from "./describe";
import { parseAuditEvent, parseRecord, parseToken } from "./parse";
import { upsertLine } from "./lines";
import type { AuditEvent, CallRecord, Check } from "./types";

const event = (over: Partial<AuditEvent>): AuditEvent => ({
  at: "", operation: "identity_check", outcome: "allowed", reason: "", details: {}, ...over,
});
const check = (verdict: Check["verdict"]): Check => ({ name: "x", verdict, detail: "" });

describe("parsing what the server sends", () => {
  it("accepts a gateway event and fills in what is missing", () => {
    const parsed = parseAuditEvent(JSON.stringify({ operation: "offer_slots", outcome: "allowed" }));
    expect(parsed).toMatchObject({ operation: "offer_slots", reason: "", details: {} });
  });
  it.each(["not json", "[]", "{}", '{"operation":"x","outcome":"maybe"}'])(
    "turns %s into null instead of throwing",
    (text) => expect(parseAuditEvent(text)).toBeNull(),
  );
  it("refuses a token response that lacks a field", () => {
    expect(() => parseToken({ url: "wss://x", token: "t" })).toThrow();
    expect(parseToken({ url: "wss://x", token: "t", room: "web-1" }).room).toBe("web-1");
  });
  it("treats an unknown verdict as not run, never as a pass", () => {
    const record = parseRecord({ checks: [{ name: "a", verdict: "great" }], appointment_after: null });
    expect(record.checks[0]?.verdict).toBe("not_run");
    expect(record.appointment_after).toBeNull();
  });
});

describe("describing events", () => {
  it("shows a refusal with its reason in words", () => {
    expect(describeEvent(event({ outcome: "refused", reason: "no_match" })).detail).toBe("Refused: no match");
  });
  it("shows what the caller said when a change was committed", () => {
    const e = event({ operation: "commit_change", details: { confirmation: { said: "Yep." } } });
    expect(describeEvent(e).detail).toBe("She said: “Yep.”");
  });
  it("counts offered times without showing the ids", () => {
    const e = event({ operation: "offer_slots", details: { offers: ["option-aaaa", "option-bbbb"] } });
    expect(describeEvent(e).detail).toContain("2 times offered");
    expect(describeEvent(e).detail).not.toContain("option-");
  });
  it("falls back to the raw operation name for one it does not know", () => {
    expect(describeEvent(event({ operation: "brand_new" })).title).toBe("brand_new");
  });
});

describe("summarising the review", () => {
  it("does not call a skipped check a pass", () => {
    expect(summariseChecks([check("pass"), check("pass"), check("not_run")])).toBe(
      "2 of 3 checks passed; 1 could not run.",
    );
  });
  it("puts a failure first", () => {
    expect(summariseChecks([check("fail"), check("not_run")])).toContain("1 of 2 checks need a person");
    expect(summariseChecks([check("pass")])).toBe("All 1 checks passed.");
  });
  it("names the checks and states in words", () => {
    expect(checkTitle({ name: "changes_were_confirmed", verdict: "pass", detail: "" })).toContain("clear yes");
    expect(agentStateLabel("thinking")).toBe("Thinking");
  });
});

describe("the transcript", () => {
  it("replaces a draft with the same id and keeps order", () => {
    const first = [{ id: "a", speaker: "caller" as const, text: "my na", final: false }];
    const next = upsertLine(upsertLine(first, { id: "b", speaker: "emily", text: "Hi", final: true }), {
      id: "a", speaker: "caller", text: "my name is Alex", final: true,
    });
    expect(next.map((l) => l.id)).toEqual(["a", "b"]);
    expect(next[0]?.text).toBe("my name is Alex");
  });
});

describe("waiting for the call record", () => {
  const record: CallRecord = { ended_because: "caller_hung_up", appointment_after: null, checks: [] };
  it("polls until the record exists", async () => {
    const answers = [null, null, record];
    const fetcher = vi.fn(async () => answers.shift() ?? null);
    const sleep = vi.fn(async () => {});
    expect(await waitForRecord("web-1", { fetcher, sleep })).toBe(record);
    expect(fetcher).toHaveBeenCalledTimes(3);
    expect(sleep).toHaveBeenCalledTimes(2);
  });
  it("gives up with null instead of waiting forever", async () => {
    const fetcher = vi.fn(async () => null);
    expect(await waitForRecord("web-1", { attempts: 3, fetcher, sleep: async () => {} })).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(3);
  });
});
