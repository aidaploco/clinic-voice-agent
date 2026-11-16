import { agentStateLabel } from "./describe";

interface Props {
  agentState: string;
  live: boolean;
  elapsed: string;
  note: { text: string; problem: boolean };
  busy: boolean;
  phone: "idle" | "confirm" | "dialling";
  onStart: () => void;
  onHangUp: () => void;
  onPhone: () => void;
  onPhoneCancel: () => void;
}

const bars = Array.from({ length: 7 }, (_, i) => i);

export function CallCard({
  agentState,
  live,
  elapsed,
  note,
  busy,
  phone,
  onStart,
  onHangUp,
  onPhone,
  onPhoneCancel,
}: Props) {
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
          <>
            <button className="primary" onClick={onStart} disabled={busy || phone !== "idle"}>
              Start a call
            </button>
            {phone === "confirm" ? (
              <span className="confirm" role="group" aria-label="Confirm ringing your phone">
                <span>Ring your phone now?</span>
                <button className="primary" onClick={onPhone}>
                  Yes, ring it
                </button>
                <button className="secondary" onClick={onPhoneCancel}>
                  Cancel
                </button>
              </span>
            ) : (
              <button className="secondary" onClick={onPhone} disabled={busy || phone === "dialling"}>
                {phone === "dialling" ? "Ringing your phone\u2026" : "Call my phone"}
              </button>
            )}
          </>
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
