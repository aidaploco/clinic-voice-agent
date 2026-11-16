import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import * as api from "./api";
import { CallList } from "./CallList";
import { describeEnding, describeOutcome, describeStarted, reviewChip } from "./describe";
import { parseRecord, parseSummaries } from "./parse";
import type { CallRecord, CallSummary } from "./types";

const call = (over: Partial<CallSummary> = {}): CallSummary => ({
  id: "web-0a1b2c3d",
  channel: "browser",
  direction: null,
  started: "2026-11-15T20:54:00",
  ended_because: "agent_ended_call",
  appointment_after: { start: "2026-11-20T09:00", status: "confirmed", practitioner: "Dr. L" },
  checks: { pass: 3, fail: 0, not_run: 0 },
  turns: 5,
  changed: true,
  ...over,
});

describe("wording for the call list", () => {
  const now = new Date(2026, 10, 15, 22, 0);
  it("says today, yesterday or the date", () => {
    expect(describeStarted("2026-11-15T20:54:00", now)).toBe("Today, 8:54 PM");
    expect(describeStarted("2026-11-14T09:02:00", now)).toBe("Yesterday, 9:02 AM");
    expect(describeStarted("2026-11-10T18:00:00", now)).toBe("Nov 10, 6:00 PM");
    expect(describeStarted("not a time", now)).toBe("Unknown time");
  });
  it("says how a call ended, including endings it has never seen", () => {
    expect(describeEnding("silence")).toBe("Line went silent");
    expect(describeEnding("service_failed:STT")).toBe("A service failed");
    expect(describeEnding("something_new")).toBe("something new");
    expect(describeEnding("")).toBe("Unknown");
  });
  it("says what became of the appointment, or that nobody was verified", () => {
    expect(describeOutcome(call())).toBe("confirmed, Fri 9:00 AM");
    expect(describeOutcome({ appointment_after: null })).toBe("No patient verified");
  });
  it("never calls a review that could not run a pass, and puts a failure first", () => {
    expect(reviewChip({ pass: 3, fail: 0, not_run: 0 })).toEqual({ label: "All passed", kind: "pass" });
    expect(reviewChip({ pass: 2, fail: 0, not_run: 1 })).toEqual({ label: "2 of 3 passed", kind: "not_run" });
    expect(reviewChip({ pass: 1, fail: 1, not_run: 1 })).toEqual({ label: "1 to read", kind: "fail" });
    expect(reviewChip({ pass: 0, fail: 0, not_run: 0 }).label).toBe("No review");
  });
});

describe("parsing the call list and a past call", () => {
  it("drops a row that is not well formed and fills in what is missing", () => {
    const rows = parseSummaries({ calls: [{ id: "web-1", channel: "weird" }, { nope: true }, null, { id: "" }] });
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ id: "web-1", channel: "other", turns: 0, changed: false });
    expect(parseSummaries("nonsense")).toEqual([]);
    expect(parseSummaries({ calls: "no" })).toEqual([]);
  });
  it("keeps which calls Emily placed", () => {
    const rows = parseSummaries({ calls: [{ id: "phone-out-1", direction: "outbound" }, { id: "phone-2", direction: "sideways" }] });
    expect(rows.map((r) => r.direction)).toEqual(["outbound", null]);
  });
  it("reads a past call's transcript and gateway events, and ignores malformed ones", () => {
    const record = parseRecord({
      started: "2026-11-15T20:54:00",
      transcript: [{ speaker: "agent", text: "Hello" }, { speaker: "caller", text: "Hi" }, 7],
      audit: [{ operation: "offer_slots", outcome: "allowed" }, { operation: "x", outcome: "maybe" }, "no"],
      checks: [],
    });
    expect(record.transcript.map((l) => [l.speaker, l.text])).toEqual([["emily", "Hello"], ["caller", "Hi"]]);
    expect(new Set(record.transcript.map((l) => l.id)).size).toBe(2);
    expect(record.audit.map((e) => e.operation)).toEqual(["offer_slots"]);
  });
});

describe("the call list", () => {
  const rows = [
    call(),
    call({ id: "phone-aaaaaaaaaa", channel: "phone", changed: false, ended_because: "caller_hung_up" }),
    call({ id: "test-bbbbbbbb", channel: "test", checks: { pass: 2, fail: 0, not_run: 1 } }),
  ];
  const none = () => {};

  it("shows each call with how it came in, how it ended and its review", () => {
    render(<CallList calls={rows} state="ready" openId={null} onOpen={none} onRefresh={none} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByText("Phone", { selector: ".chip" })).toBeInTheDocument();
    expect(screen.getByText("Caller hung up", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("2 of 3 passed")).toHaveClass("not_run");
    expect(screen.getAllByText("changed the appointment")).toHaveLength(2);
  });
  it("says which calls Emily placed", () => {
    const rows2 = [call({ id: "phone-out-aaaaaaaa", channel: "phone", direction: "outbound" }), call({ channel: "phone", id: "phone-bbbbbbbb" })];
    render(<CallList calls={rows2} state="ready" openId={null} onOpen={none} onRefresh={none} />);
    expect(screen.getAllByText("Emily called")).toHaveLength(1);
  });
  it("filters by how the call came in", async () => {
    render(<CallList calls={rows} state="ready" openId={null} onOpen={none} onRefresh={none} />);
    await userEvent.click(screen.getByRole("button", { name: "Phone" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "All" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });
  it("opens the call that was clicked", async () => {
    const onOpen = vi.fn();
    render(<CallList calls={rows} state="ready" openId={null} onOpen={onOpen} onRefresh={none} />);
    await userEvent.click(within(screen.getAllByRole("listitem")[1] as HTMLElement).getByRole("button"));
    expect(onOpen).toHaveBeenCalledWith(rows[1]);
  });
  it("says so when there are no calls, and when they could not be loaded", () => {
    const { rerender } = render(<CallList calls={[]} state="ready" openId={null} onOpen={none} onRefresh={none} />);
    expect(screen.getByText(/No calls yet/)).toBeInTheDocument();
    rerender(<CallList calls={[]} state="error" openId={null} onOpen={none} onRefresh={none} />);
    expect(screen.getByText(/Could not load the calls/)).toBeInTheDocument();
  });
});

describe("opening a past call from the page", () => {
  const past: CallRecord = {
    started: "2026-11-15T20:54:00",
    transcript: [
      { id: "p0", speaker: "emily", text: "Thank you for calling.", final: true },
      { id: "p1", speaker: "caller", text: '<img src=x onerror="window.pwned=true">', final: true },
    ],
    audit: [{ at: "1", operation: "offer_slots", outcome: "allowed", reason: "", details: { offers: ["a"] } }],
    ended_because: "caller_hung_up",
    appointment_after: null,
    checks: [{ name: "said_matches_done", verdict: "pass", detail: "" }],
  };

  it("shows the transcript, the gateway's decisions and the review, as plain text, and goes back to live", async () => {
    vi.spyOn(api, "fetchCalls").mockResolvedValue([call()]);
    vi.spyOn(api, "fetchRecord").mockResolvedValue(past);
    const { container } = render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Today|Nov|Yesterday/ }));
    expect(await screen.findByText(/Viewing a past call/)).toBeInTheDocument();
    expect(screen.getByText("Thank you for calling.")).toBeInTheDocument();
    expect(screen.getByText("Looked up free times")).toBeInTheDocument();
    expect(screen.getByText("All 1 checks passed.")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Back to live" }));
    expect(screen.queryByText(/Viewing a past call/)).toBeNull();
    expect(screen.queryByText("Thank you for calling.")).toBeNull();
  });
  it("says so when the list cannot be loaded and the call cannot be opened", async () => {
    vi.spyOn(api, "fetchCalls").mockRejectedValue(new Error("down"));
    render(<App />);
    expect(await screen.findByText(/Could not load the calls/)).toBeInTheDocument();
  });
});


describe("ringing the owner's phone from the page", () => {
  const record: CallRecord = {
    started: "2026-11-15T20:54:00",
    transcript: [{ id: "p0", speaker: "emily", text: "Hello, this is Emily.", final: true }],
    audit: [],
    ended_because: "agent_ended_call",
    appointment_after: null,
    checks: [{ name: "said_matches_done", verdict: "pass", detail: "" }],
  };
  beforeEach(() => {
    vi.spyOn(api, "fetchCalls").mockResolvedValue([]);
  });

  it("only asks on the first click: nothing is dialled until it is confirmed", async () => {
    const dial = vi.spyOn(api, "callMyPhone").mockResolvedValue("phone-out-aaaaaaaa");
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Call my phone" }));
    expect(screen.getByText("Ring your phone now?")).toBeInTheDocument();
    expect(dial).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Call my phone" })).toBeEnabled();
    expect(dial).not.toHaveBeenCalled();
  });

  it("dials once it is confirmed, then shows the call when it ends", async () => {
    const dial = vi.spyOn(api, "callMyPhone").mockResolvedValue("phone-out-aaaaaaaa");
    vi.spyOn(api, "waitForRecord").mockResolvedValue(record);
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Call my phone" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, ring it" }));
    expect(await screen.findByText("Hello, this is Emily.")).toBeInTheDocument();
    expect(dial).toHaveBeenCalledTimes(1);
    expect(screen.getByText("All 1 checks passed.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Call my phone" })).toBeEnabled();
  });

  it("says why when the phone could not be rung, and lets the owner try again", async () => {
    vi.spyOn(api, "callMyPhone").mockRejectedValue(new Error("no worker joined the room, so the phone was not rung"));
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Call my phone" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, ring it" }));
    expect(await screen.findByText(/Could not call your phone: no worker joined/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Call my phone" })).toBeEnabled();
  });
});
