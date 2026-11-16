import { useRoomContext, useVoiceAssistant, useRemoteParticipants } from "@livekit/components-react";
import { useEffect } from "react";
import { parseAuditEvent } from "./parse";
import type { AuditEvent, Line } from "./types";

const TRANSCRIPTION = "lk.transcription";
const GATEWAY_EVENTS = "clinic.audit";
const JOIN_TIMEOUT_MS = 10_000;

interface Props {
  onLine: (line: Line) => void;
  onEvent: (event: AuditEvent) => void;
  onAgentState: (state: string) => void;
  onNote: (text: string, problem: boolean) => void;
}

/**
 * Lives inside the room and renders nothing. It turns the room's streams into calls on its props:
 * the transcript, the gateway's decisions, and the agent's state. It also notices when nobody
 * joins, the usual sign of a worker that is not running.
 */
export function RoomStreams({ onLine, onEvent, onAgentState, onNote }: Props) {
  const room = useRoomContext();
  const { state } = useVoiceAssistant();
  const remote = useRemoteParticipants();

  useEffect(() => {
    onAgentState(state);
  }, [state, onAgentState]);

  useEffect(() => {
    room.registerTextStreamHandler(TRANSCRIPTION, async (reader, from) => {
      const id = reader.info.attributes?.["lk.segment_id"] ?? reader.info.id;
      const speaker = from.identity === room.localParticipant.identity ? "caller" : "emily";
      let text = "";
      for await (const chunk of reader) {
        text += chunk;
        onLine({ id, speaker, text, final: false });
      }
      onLine({ id, speaker, text, final: true });
    });
    room.registerTextStreamHandler(GATEWAY_EVENTS, async (reader) => {
      const event = parseAuditEvent(await reader.readAll());
      if (event) onEvent(event);
    });
    return () => {
      room.unregisterTextStreamHandler(TRANSCRIPTION);
      room.unregisterTextStreamHandler(GATEWAY_EVENTS);
    };
  }, [room, onLine, onEvent]);

  const someoneJoined = remote.length > 0;
  useEffect(() => {
    if (someoneJoined) return;
    const timer = setTimeout(
      () =>
        onNote(
          "Emily has not joined the call. Is the worker running? In another terminal: " +
            "uv run python -m clinic_voice_agent.worker start",
          true,
        ),
      JOIN_TIMEOUT_MS,
    );
    return () => clearTimeout(timer);
  }, [someoneJoined, onNote]);

  return null;
}
