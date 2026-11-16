import { LiveKitRoom, RoomAudioRenderer, StartAudio } from "@livekit/components-react";
import { useCallback, useEffect, useState } from "react";
import { fetchCalls, fetchRecord, fetchToken, waitForRecord } from "./api";
import { CallCard } from "./CallCard";
import { CallList } from "./CallList";
import { describeStarted } from "./describe";
import { GatewayEvents } from "./GatewayEvents";
import { ReviewPanel } from "./ReviewPanel";
import { RoomStreams } from "./RoomStreams";
import { Transcript } from "./Transcript";
import { upsertLine } from "./lines";
import type { AuditEvent, CallRecord, CallSummary, Line, TokenResponse } from "./types";
import { useElapsed } from "./useElapsed";

type Phase = "idle" | "connecting" | "live";

export function App() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [call, setCall] = useState<TokenResponse | null>(null);
  const [wantConnected, setWantConnected] = useState(false);
  const [lines, setLines] = useState<Line[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [record, setRecord] = useState<CallRecord | null>(null);
  const [agentState, setAgentState] = useState("idle");
  const [note, setNote] = useState({ text: "", problem: false });
  const elapsed = useElapsed(phase === "live");
  const say = useCallback((text: string, problem = false) => setNote({ text, problem }), []);
  const onLine = useCallback((line: Line) => setLines((all) => upsertLine(all, line)), []);
  const onEvent = useCallback((event: AuditEvent) => setEvents((all) => [...all, event]), []);

  const [calls, setCalls] = useState<CallSummary[]>([]);
  const [listState, setListState] = useState<"loading" | "ready" | "error">("loading");
  const [viewing, setViewing] = useState<{ summary: CallSummary; record: CallRecord } | null>(null);

  const refreshCalls = useCallback(async () => {
    try {
      setCalls(await fetchCalls());
      setListState("ready");
    } catch {
      setListState("error");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchCalls().then(
      (rows) => {
        if (cancelled) return;
        setCalls(rows);
        setListState("ready");
      },
      () => {
        if (!cancelled) setListState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  async function openCall(summary: CallSummary) {
    try {
      const opened = await fetchRecord(summary.id);
      if (opened) setViewing({ summary, record: opened });
      else say("That call's record is not there any more.", true);
    } catch (error) {
      say(`Could not open the call: ${error instanceof Error ? error.message : String(error)}`, true);
    }
  }

  async function start() {
    setViewing(null);
    setLines([]);
    setEvents([]);
    setRecord(null);
    setAgentState("connecting");
    say("");
    setPhase("connecting");
    try {
      setCall(await fetchToken());
      setWantConnected(true);
    } catch (error) {
      say(`Could not start the call: ${error instanceof Error ? error.message : String(error)}`, true);
      setAgentState("idle");
      setPhase("idle");
    }
  }

  async function ended() {
    const room = call?.room;
    setPhase("idle");
    setWantConnected(false);
    setCall(null);
    setAgentState("idle");
    if (!room) return;
    say("The call has ended. Waiting for the review…");
    const result = await waitForRecord(room);
    if (result) {
      setRecord(result);
      say("");
      void refreshCalls();
    } else {
      say("The call record was not written in time. Check the worker.", true);
    }
  }

  return (
    <>
      <header className="top">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <span>Quillbrook Physio</span>
        </div>
        <span className="demo">Demo: a fictional clinic, invented patients</span>
      </header>
      <main>
        <section className="call card" aria-label="Call">
          <CallCard
            agentState={agentState}
            live={phase === "live"}
            busy={phase === "connecting"}
            elapsed={elapsed}
            note={note}
            onStart={start}
            onHangUp={() => setWantConnected(false)}
          />
          {viewing && (
            <p className="viewing" role="status">
              Viewing a past call ({describeStarted(viewing.record.started)}).{" "}
              <button className="link" onClick={() => setViewing(null)}>
                Back to live
              </button>
            </p>
          )}
          <Transcript lines={viewing ? viewing.record.transcript : lines} />
        </section>
        <aside className="behind card" aria-label="Behind the scenes">
          <GatewayEvents events={viewing ? viewing.record.audit : events} />
          {(viewing?.record ?? record) && <ReviewPanel record={(viewing?.record ?? record) as CallRecord} />}
        </aside>
      </main>
      <div className="below">
        <CallList
          calls={calls}
          state={listState}
          openId={viewing?.summary.id ?? null}
          onOpen={(c) => void openCall(c)}
          onRefresh={() => void refreshCalls()}
        />
      </div>
      {call && (
        <LiveKitRoom
          serverUrl={call.url}
          token={call.token}
          connect={wantConnected}
          audio
          video={false}
          onConnected={() => {
            setPhase("live");
            say("Connected. Emily will greet you.");
          }}
          onDisconnected={() => void ended()}
          onMediaDeviceFailure={() => say("Microphone unavailable: you can listen, but she cannot hear you.", true)}
          onError={(error) => say(`Call problem: ${error.message}`, true)}
        >
          <RoomAudioRenderer />
          <StartAudio label="Click to hear Emily" className="primary" />
          <RoomStreams onLine={onLine} onEvent={onEvent} onAgentState={setAgentState} onNote={say} />
        </LiveKitRoom>
      )}
    </>
  );
}
