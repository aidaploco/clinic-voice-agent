import { useState } from "react";
import { channelLabel, describeEnding, describeOutcome, describeStarted, reviewChip } from "./describe";
import type { CallSummary, Channel } from "./types";

type Filter = "all" | Channel;
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "phone", label: "Phone" },
  { key: "browser", label: "Browser" },
  { key: "test", label: "Scripted tests" },
];

interface Props {
  calls: CallSummary[];
  state: "loading" | "ready" | "error";
  openId: string | null;
  onOpen: (call: CallSummary) => void;
  onRefresh: () => void;
}

export function CallList({ calls, state, openId, onOpen, onRefresh }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const shown = filter === "all" ? calls : calls.filter((c) => c.channel === filter);
  return (
    <section className="card calls" aria-label="Recent calls">
      <div className="calls-head">
        <h2>Recent calls</h2>
        <div className="filters" role="group" aria-label="Show calls from">
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              className="filter"
              aria-pressed={filter === key}
              onClick={() => setFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <button className="secondary small" onClick={onRefresh}>
          Refresh
        </button>
      </div>
      {state === "error" && <p className="note problem">Could not load the calls. Is the page server running?</p>}
      {state === "loading" && calls.length === 0 && <p className="empty">Loading calls…</p>}
      {state === "ready" && shown.length === 0 && <p className="empty">No calls yet. Start one above.</p>}
      <ol className="call-rows">
        {shown.map((call) => {
          const chip = reviewChip(call.checks);
          return (
            <li key={call.id}>
              <button
                className="call-row"
                aria-current={openId === call.id}
                onClick={() => onOpen(call)}
              >
                <span className="row-main">
                  <span className="row-when">{describeStarted(call.started)}</span>
                  <span className="chip channel">{channelLabel(call.channel)}</span>
                  {call.changed && <span className="chip changed">changed the appointment</span>}
                </span>
                <span className="row-detail">
                  {describeEnding(call.ended_because)} · {describeOutcome(call)} · {call.turns}{" "}
                  {call.turns === 1 ? "turn" : "turns"}
                </span>
                <span className={`chip ${chip.kind}`}>{chip.label}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
