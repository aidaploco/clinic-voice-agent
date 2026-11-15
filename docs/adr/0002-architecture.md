# ADR-0002: Architecture

Status: accepted, 2026-11-15

## Context

A voice agent has four hard parts: taking turns naturally, acting without making the caller wait, never doing the wrong thing on a caller's say-so, and knowing whether any of it actually works. The architecture is chosen to make each of those visible and testable.

## Decision

**Workers dispatched per call.** The agent runs as a LiveKit Agents worker. Workers register with the media server, which hands each new call to one of them. Scaling is adding workers; nothing in the application starts or supervises processes.

**Tools during the call, behind a gateway.** The model can find slots, move, cancel and confirm appointments, take messages and hand over. It never touches the clinic's records directly. Every tool call goes through a gateway that:
- holds a capability for this call only, limited to the one verified patient;
- hands out free slots as server-issued ids, so the model cannot name a time that was not offered;
- treats a change as held until the caller has heard it read back and clearly agreed;
- logs every action with the words that authorised it.

**An explicit conversation flow.** Who is calling, what they want, doing it, confirming it, closing. Tools unlock only after the identity step succeeds. The model chooses words; it does not choose which step it is in.

**Identity with a second factor.** The caller's number suggests who they might be. A date of birth confirms it. Nothing about an appointment is said before that.

**Languages as data.** Each language is a row: which speech-to-text and text-to-speech to use, which voice, which evals it must pass. The flow and the tools are shared.

**Two voice stacks behind one agent.** The default chains speech-to-text, a language model and text-to-speech. A second configuration uses one speech-to-speech model. Both run the same flow and tools, so they can be compared on the same evals.

**Managed media.** LiveKit Cloud carries the audio and the phone trunk. The project's effort goes into the agent, not into running a media server.

**Evals as part of the build.** Text-level conversations gate every change. Audio-level runs, with simulated callers speaking through real rooms, produce the published numbers.

## Rejected

- **A hosted, no-code voice-agent product.** It hides the parts this project is meant to show.
- **Tools without a gateway, guarded by the prompt.** A prompt is a habit, not a guarantee; a caller's words reach the model directly.
- **One long prompt instead of a flow.** It works in a demo and drifts under pressure: skipped identity checks, actions taken before confirmation.
- **Self-hosting the media server.** Real work, and worth doing where it is the product. Here it would be most of the effort and none of the point.
- **Only a speech-to-speech model.** Faster and more natural, but harder to constrain and to debug. Worth measuring against the chain, not assuming.

## Revisit when

The evals show the flow is too rigid for how patients actually speak, or a speech-to-speech model matches the chain on task completion, at which point it may become the default.
