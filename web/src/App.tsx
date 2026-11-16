import { LiveKitRoom, RoomAudioRenderer, StartAudio } from "@livekit/components-react";
import { useCallback, useState } from "react";
import { fetchToken, waitForRecord } from "./api";
import { CallCard } from "./CallCard";
import { GatewayEvents } from "./GatewayEvents";
import { ReviewPanel } from "./ReviewPanel";
import { RoomStreams } from "./RoomStreams";
import { Transcript } from "./Transcript";
import { upsertLine } from "./lines";
import type { AuditEvent, CallRecord, Line, TokenResponse } from "./types";
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

  async function start() {
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
          <Transcript lines={lines} />
        </section>
        <aside className="behind card" aria-label="Behind the scenes">
          <GatewayEvents events={events} />
          {record && <ReviewPanel record={record} />}
        </aside>
      </main>
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
