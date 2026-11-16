import { parseRecord, parseToken } from "./parse";
import type { CallRecord, TokenResponse } from "./types";

export async function fetchToken(): Promise<TokenResponse> {
  const response = await fetch("/api/token", { method: "POST" });
  if (!response.ok) throw new Error((await response.text()) || "could not get a call token");
  return parseToken(await response.json());
}

/** The finished record, or null while the worker has not written it yet. */
export async function fetchRecord(room: string): Promise<CallRecord | null> {
  const response = await fetch(`/api/calls/${encodeURIComponent(room)}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`the call record request failed (${response.status})`);
  return parseRecord(await response.json());
}

interface Waiting {
  attempts?: number;
  delayMs?: number;
  fetcher?: (room: string) => Promise<CallRecord | null>;
  sleep?: (ms: number) => Promise<void>;
}

/** The worker writes the record after the call closes, and the review can take a while. */
export async function waitForRecord(room: string, options: Waiting = {}): Promise<CallRecord | null> {
  const {
    attempts = 40,
    delayMs = 1500,
    fetcher = fetchRecord,
    sleep = (ms: number) => new Promise<void>((done) => setTimeout(done, ms)),
  } = options;
  for (let i = 0; i < attempts; i++) {
    const record = await fetcher(room);
    if (record) return record;
    await sleep(delayMs);
  }
  return null;
}
