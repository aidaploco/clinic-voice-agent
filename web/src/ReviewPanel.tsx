import { checkTitle, summariseChecks } from "./describe";
import type { CallRecord } from "./types";

export function ReviewPanel({ record }: { record: CallRecord }) {
  const after = record.appointment_after;
  return (
    <section aria-label="Review after the call">
      <h2>Review after the call</h2>
      <p className="sub">{summariseChecks(record.checks)}</p>
      <ul className="checks">
        {record.checks.map((check) => (
          <li key={check.name}>
            <div className="ev-head">
              <span className="ev-name">{checkTitle(check)}</span>
              <span className={`chip ${check.verdict}`}>{check.verdict.replace("_", " ")}</span>
            </div>
            {check.detail && <div className="ev-detail">{check.detail}</div>}
          </li>
        ))}
      </ul>
      <dl className="facts">
        <dt>Call ended because</dt>
        <dd>{record.ended_because.replaceAll("_", " ")}</dd>
        <dt>Appointment afterwards</dt>
        <dd>
          {after
            ? `${after.status}, ${after.start.replace("T", " ")} with ${after.practitioner}`
            : "no patient was verified"}
        </dd>
      </dl>
    </section>
  );
}
