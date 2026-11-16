import { useEffect, useRef } from "react";
import type { Line } from "./types";

export function Transcript({ lines }: { lines: Line[] }) {
  const end = useRef<HTMLLIElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "nearest" });
  }, [lines]);
  return (
    <>
      <h2>Transcript</h2>
      <ol className="transcript" aria-live="polite">
        {lines.length === 0 && <li className="empty">The conversation appears here.</li>}
        {lines.map((line) => (
          <li key={line.id} className={`${line.speaker === "caller" ? "you" : "her"}${line.final ? "" : " interim"}`}>
            <span className="who-label">{line.speaker === "caller" ? "You" : "Emily"}</span>
            <span>{line.text}</span>
          </li>
        ))}
        <li ref={end} aria-hidden="true" style={{ padding: 0 }} />
      </ol>
    </>
  );
}
