import type { Line } from "./types";

/** Insert a line, or replace the one with the same id (a caller's words arrive as growing drafts). */
export function upsertLine(lines: Line[], line: Line): Line[] {
  const at = lines.findIndex((l) => l.id === line.id);
  if (at === -1) return [...lines, line];
  return lines.map((l, i) => (i === at ? line : l));
}
