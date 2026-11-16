// The page: join a call, show the transcript and the gateway's decisions live, then the review.
// Everything that came from a call goes in through textContent, never as markup.
(() => {
  const { Room, RoomEvent, Track } = window.LivekitClient;
  const $ = (id) => document.getElementById(id);
  const els = {
    start: $("start"), end: $("end"), timer: $("timer"), note: $("note"), state: $("state"),
    bars: $("bars"), avatar: $("avatar"), transcript: $("transcript"), events: $("events"),
    review: $("review"), summary: $("review-summary"), checks: $("checks"), facts: $("facts"),
  };

  const STATE_LABEL = { idle: "Not on a call", connecting: "Connecting", initializing: "Connecting",
    listening: "Listening", thinking: "Thinking", speaking: "Speaking" };
  const EVENT_LABEL = {
    identity_check: "Checked who is calling", offer_slots: "Looked up free times",
    propose_change: "Proposed a change (nothing changed yet)", commit_change: "Committed the change",
    take_message: "Took a message for the clinic",
  };
  const CHECK_LABEL = {
    changes_follow_identity: "Nothing was changed before the caller was verified",
    changes_were_confirmed: "Every change followed a clear yes",
    said_matches_done: "What she told the caller matches what was done",
  };

  let room = null, roomName = null, tick = null, began = 0, ended = false;
  const lines = new Map();

  function setState(state) {
    els.state.dataset.state = state === "listening" || state === "thinking" || state === "speaking" ? state : "idle";
    els.state.textContent = STATE_LABEL[state] || state;
    els.bars.className = "bars " + (state === "speaking" || state === "thinking" ? state : "");
    els.avatar.classList.toggle("speaking", state === "speaking");
  }
  function say(text, problem = false) { els.note.textContent = text; els.note.classList.toggle("problem", problem); }
  function clearEmpty(list) { list.querySelector(".empty")?.remove(); }

  function addLine(key, who, text, final) {
    clearEmpty(els.transcript);
    let li = lines.get(key);
    if (!li) {
      li = document.createElement("li");
      const label = document.createElement("span"); label.className = "who-label"; label.textContent = who === "you" ? "You" : "Emily";
      const body = document.createElement("span"); body.className = "body";
      li.append(label, body); li.classList.add(who); lines.set(key, li); els.transcript.append(li);
    }
    li.querySelector(".body").textContent = text;
    li.classList.toggle("interim", !final);
    els.transcript.scrollTop = els.transcript.scrollHeight;
  }

  function detailOf(e) {
    const d = e.details || {};
    if (e.outcome === "refused") return "Refused: " + (e.reason || "not allowed").replaceAll("_", " ");
    if (e.operation === "identity_check") return "Attempt " + (d.attempt ?? "?") + ": name and date of birth matched";
    if (e.operation === "offer_slots") return (d.offers || []).length + " times offered, under ids made up for this call";
    if (e.operation === "propose_change") return "Asked: " + (d.read_back || "");
    if (e.operation === "commit_change") return "She said: “" + (d.confirmation?.said || "") + "”";
    return "";
  }
  function addEvent(e) {
    clearEmpty(els.events);
    const li = document.createElement("li");
    const head = document.createElement("div"); head.className = "ev-head";
    const name = document.createElement("span"); name.className = "ev-name"; name.textContent = EVENT_LABEL[e.operation] || e.operation;
    const chip = document.createElement("span"); chip.className = "chip " + e.outcome; chip.textContent = e.outcome;
    head.append(name, chip);
    const detail = document.createElement("div"); detail.className = "ev-detail"; detail.textContent = detailOf(e);
    li.append(head, detail); els.events.append(li);
  }

  function reset() {
    lines.clear(); ended = false;
    els.transcript.replaceChildren(Object.assign(document.createElement("li"), { className: "empty", textContent: "The conversation appears here." }));
    els.events.replaceChildren(Object.assign(document.createElement("li"), { className: "empty", textContent: "Nothing yet." }));
    els.review.hidden = true; els.checks.replaceChildren(); els.facts.replaceChildren();
  }

  function startTimer() {
    began = Date.now(); els.timer.hidden = false;
    tick = setInterval(() => {
      const s = Math.floor((Date.now() - began) / 1000);
      els.timer.textContent = Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
    }, 500);
  }

  async function startCall() {
    reset(); els.start.disabled = true; say(""); setState("connecting");
    try {
      const r = await fetch("/api/token", { method: "POST" });
      if (!r.ok) throw new Error((await r.text()) || "could not get a call token");
      const { url, token, room: name } = await r.json();
      roomName = name;
      room = new Room();
      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Audio) { const a = track.attach(); a.hidden = true; document.body.append(a); }
      });
      room.on(RoomEvent.ParticipantAttributesChanged, (attrs, p) => {
        if (attrs["lk.agent.state"] && p.identity !== room.localParticipant.identity) setState(attrs["lk.agent.state"]);
      });
      room.registerTextStreamHandler("lk.transcription", async (reader, info) => {
        const id = reader.info.attributes?.["lk.segment_id"] || reader.info.id;
        const mine = info.identity === room.localParticipant.identity;
        let text = "";
        for await (const chunk of reader) { text += chunk; addLine(id, mine ? "you" : "her", text, false); }
        addLine(id, mine ? "you" : "her", text, true);
      });
      room.registerTextStreamHandler("clinic.audit", async (reader) => {
        try { addEvent(JSON.parse(await reader.readAll())); } catch { /* a malformed event is skipped */ }
      });
      room.on(RoomEvent.Disconnected, onEnded);
      await room.connect(url, token);
      await room.startAudio();            // inside the click: browsers block sound otherwise
      els.start.hidden = true; els.end.hidden = false; startTimer(); say("Connected. Emily will greet you.");
      // Only the agent ever joins the room. If nobody has after a few seconds, the usual cause
      // is that the worker is not running, and a silent page gives no hint of that.
      setTimeout(() => {
        if (room && room.state === "connected" && room.remoteParticipants.size === 0) {
          say("Emily has not joined the call. Is the worker running? In another terminal: "
            + "uv run python -m clinic_voice_agent.worker start", true);
        }
      }, 10000);
      // Not awaited before the controls show: the browser's permission prompt can stay open.
      room.localParticipant.setMicrophoneEnabled(true).catch(() =>
        say("Microphone unavailable: you can listen, but she cannot hear you.", true));
    } catch (err) {
      say("Could not start the call: " + err.message, true); setState("idle"); els.start.disabled = false;
    }
  }

  async function onEnded() {
    if (ended) return; ended = true;
    clearInterval(tick); els.end.hidden = true; els.timer.hidden = true; els.start.hidden = false; els.start.disabled = false;
    setState("idle"); say("The call has ended. Waiting for the review…");
    for (let i = 0; i < 40; i++) {                    // the worker writes the record after the call closes
      const r = await fetch("/api/calls/" + roomName);
      if (r.ok) { showReview(await r.json()); return; }
      await new Promise((ok) => setTimeout(ok, 1500));
    }
    say("The call record was not written in time. Check the worker.", true);
  }

  function showReview(rec) {
    say("");
    els.review.hidden = false;
    const checks = rec.checks || [];
    const count = (v) => checks.filter((c) => c.verdict === v).length;
    const [failed, skipped] = [count("fail"), count("not_run")];
    els.summary.textContent = failed ? failed + " of " + checks.length + " checks need a person to read them."
      : skipped ? count("pass") + " of " + checks.length + " checks passed; " + skipped + " could not run."
      : "All " + checks.length + " checks passed.";
    for (const c of checks) {
      const li = document.createElement("li");
      const head = document.createElement("div"); head.className = "ev-head";
      const name = document.createElement("span"); name.className = "ev-name"; name.textContent = CHECK_LABEL[c.name] || c.name;
      const chip = document.createElement("span"); chip.className = "chip " + c.verdict; chip.textContent = c.verdict.replace("_", " ");
      head.append(name, chip); li.append(head);
      if (c.detail) { const d = document.createElement("div"); d.className = "ev-detail"; d.textContent = c.detail; li.append(d); }
      els.checks.append(li);
    }
    const after = rec.appointment_after;
    const facts = [["Call ended because", (rec.ended_because || "").replaceAll("_", " ")],
      ["Appointment afterwards", after ? after.status + ", " + after.start.replace("T", " ") + " with " + after.practitioner : "no patient was verified"]];
    for (const [k, v] of facts) {
      const dt = document.createElement("dt"); dt.textContent = k;
      const dd = document.createElement("dd"); dd.textContent = v; els.facts.append(dt, dd);
    }
  }

  els.start.addEventListener("click", startCall);
  els.end.addEventListener("click", () => room && room.disconnect());
  setState("idle");
})();
