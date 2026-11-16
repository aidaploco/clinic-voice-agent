import { agentStateLabel } from "./describe";

interface Props {
  agentState: string;
  live: boolean;
  elapsed: string;
  note: { text: string; problem: boolean };
  busy: boolean;
  onStart: () => void;
  onHangUp: () => void;
}

const bars = Array.from({ length: 7 }, (_, i) => i);

export function CallCard({ agentState, live, elapsed, note, busy, onStart, onHangUp }: Props) {
  const shown = live || busy ? agentState : "idle";
  const animated = shown === "speaking" || shown === "thinking" ? shown : "";
  return (
    <>
      <div className="who">
        <div className={`avatar${shown === "speaking" ? " speaking" : ""}`} aria-hidden="true">
          E
        </div>
        <div>
          <h1>Emily</h1>
          <p className="role">The clinic&apos;s automated receptionist</p>
        </div>
        <span className="pill" data-state={["listening", "thinking", "speaking"].includes(shown) ? shown : "idle"}>
          {agentStateLabel(shown)}
        </span>
      </div>
      <div className={`bars ${animated}`} aria-hidden="true">
        {bars.map((i) => (
          <i key={i} />
        ))}
      </div>
      <div className="actions">
        {live ? (
          <>
            <button className="secondary" onClick={onHangUp}>
              Hang up
            </button>
            <span className="timer">{elapsed}</span>
          </>
        ) : (
          <button className="primary" onClick={onStart} disabled={busy}>
            Start a call
          </button>
        )}
      </div>
      <p className={`note${note.problem ? " problem" : ""}`} role="status">
        {note.text}
      </p>
      <details className="hint" open>
        <summary>Who you are on this call</summary>
        <p>
          You are <strong>Alex Rivera</strong>, born <strong>14 March 1990</strong>, with a shoulder physiotherapy
          appointment tomorrow at three thirty in the afternoon. Try moving it, cancelling it, asking for a time she
          didn&apos;t offer, or giving the wrong date of birth.
        </p>
      </details>
    </>
  );
}
