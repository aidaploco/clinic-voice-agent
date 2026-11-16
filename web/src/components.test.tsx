import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import * as api from "./api";
import { CallCard } from "./CallCard";
import { GatewayEvents } from "./GatewayEvents";
import { ReviewPanel } from "./ReviewPanel";
import { Transcript } from "./Transcript";
import type { CallRecord } from "./types";

describe("the transcript", () => {
  it("shows what was said as text, never as markup", () => {
    const hostile = '<img src=x onerror="window.pwned=true"><b>hi</b>';
    const { container } = render(
      <Transcript lines={[{ id: "1", speaker: "caller", text: hostile, final: true }]} />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(screen.getByText(hostile)).toBeInTheDocument();
  });
  it("survives a browser whose scrollIntoView returns a Promise, as Chrome's does", () => {
    // jsdom has no scrollIntoView, so a test would never see this. In Chrome it returns a
    // Promise; an effect that returned it made React call a Promise as a cleanup function,
    // and the page went blank when the next line arrived.
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = () => Promise.resolve() as unknown as undefined;
    try {
      const line = (id: string) => ({ id, speaker: "emily" as const, text: id, final: true });
      const { rerender } = render(<Transcript lines={[line("a")]} />);
      expect(() => rerender(<Transcript lines={[line("a"), line("b")]} />)).not.toThrow();
      expect(screen.getByText("b")).toBeInTheDocument();
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });
  it("marks a draft and labels who is speaking", () => {
    render(
      <Transcript
        lines={[
          { id: "1", speaker: "emily", text: "Hello", final: true },
          { id: "2", speaker: "caller", text: "my na", final: false },
        ]}
      />,
    );
    expect(screen.getByText("Emily")).toBeInTheDocument();
    expect(screen.getByText("my na").closest("li")).toHaveClass("interim", "you");
  });
});

describe("the gateway's decisions", () => {
  it("shows allowed and refused requests with the reason", () => {
    render(
      <GatewayEvents
        events={[
          { at: "1", operation: "identity_check", outcome: "refused", reason: "no_match", details: {} },
          { at: "2", operation: "offer_slots", outcome: "allowed", reason: "", details: { offers: ["a"] } },
        ]}
      />,
    );
    expect(screen.getByText("Refused: no match")).toBeInTheDocument();
    expect(screen.getByText("refused")).toHaveClass("chip", "refused");
    expect(screen.getByText("allowed")).toHaveClass("chip", "allowed");
  });
  it("says so when nothing has happened", () => {
    render(<GatewayEvents events={[]} />);
    expect(screen.getByText("Nothing yet.")).toBeInTheDocument();
  });
});

describe("the review", () => {
  const record: CallRecord = {
    ended_because: "caller_hung_up",
    appointment_after: { start: "2026-11-17T10:30", status: "confirmed", practitioner: "Dr. Okafor" },
    checks: [
      { name: "changes_follow_identity", verdict: "pass", detail: "" },
      { name: "said_matches_done", verdict: "not_run", detail: "APIConnectionError" },
    ],
  };
  it("does not present a check that could not run as a pass", () => {
    render(<ReviewPanel record={record} />);
    expect(screen.getByText("1 of 2 checks passed; 1 could not run.")).toBeInTheDocument();
    expect(screen.getByText("not run")).toHaveClass("not_run");
    expect(screen.getByText("confirmed, 2026-11-17 10:30 with Dr. Okafor")).toBeInTheDocument();
  });
});

describe("the call card", () => {
  const base = { agentState: "idle", live: false, elapsed: "0:00", busy: false, onStart() {}, onHangUp() {} };
  it("offers Start when idle and Hang up with a timer when live", () => {
    const { rerender } = render(<CallCard {...base} note={{ text: "", problem: false }} />);
    expect(screen.getByRole("button", { name: "Start a call" })).toBeEnabled();
    rerender(<CallCard {...base} live elapsed="1:05" agentState="speaking" note={{ text: "", problem: false }} />);
    expect(screen.getByRole("button", { name: "Hang up" })).toBeInTheDocument();
    expect(screen.getByText("1:05")).toBeInTheDocument();
    expect(screen.getByText("Speaking")).toBeInTheDocument();
  });
  it("shows a problem in the status line", () => {
    render(<CallCard {...base} note={{ text: "Emily has not joined", problem: true }} />);
    expect(screen.getByRole("status")).toHaveClass("problem");
  });
});

describe("starting a call", () => {
  it("says what went wrong when no call token can be had, and lets the caller try again", async () => {
    vi.spyOn(api, "fetchToken").mockRejectedValue(new Error("the day's call cap is reached"));
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Start a call" }));
    expect(await screen.findByText(/Could not start the call: the day's call cap is reached/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start a call" })).toBeEnabled();
  });
});
