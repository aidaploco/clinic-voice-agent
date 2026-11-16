import { describeEvent } from "./describe";
import type { AuditEvent } from "./types";

export function GatewayEvents({ events }: { events: AuditEvent[] }) {
  return (
    <>
      <h2>Behind the scenes</h2>
      <p className="sub">
        Every request the model makes goes through a gateway that decides. Allowed and refused, as they happen.
      </p>
      <ol className="events">
        {events.length === 0 && <li className="empty">Nothing yet.</li>}
        {events.map((event, i) => {
          const { title, detail } = describeEvent(event);
          return (
            <li key={`${event.at}-${i}`}>
              <div className="ev-head">
                <span className="ev-name">{title}</span>
                <span className={`chip ${event.outcome}`}>{event.outcome}</span>
              </div>
              {detail && <div className="ev-detail">{detail}</div>}
            </li>
          );
        })}
      </ol>
    </>
  );
}
