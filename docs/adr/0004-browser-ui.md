# ADR-0004: A browser page for talking to Emily

Status: accepted, 2026-11-15

## Context

Today the only ways to talk to Emily are the terminal `console` command and a scripted caller. Phase 4 adds real phone calls, but a phone costs money per minute and needs a number. A page in a browser costs only the speech and model use, works for anyone who clones the repository, and is the thing a visitor to the repository can look at in a screenshot. It should also show what the agent is doing: the transcript, the gateway's allowed and refused requests, and the post-call review.

## Decision

**The page is run locally, not hosted.** `scripts/` start a small server on 127.0.0.1. A public URL would let strangers start calls that spend the owner's speech and model credit, and would break the rule that nothing stays running. Showing it publicly means a screenshot and a short recording in the README. Hosting is a separate decision for the owner.

**One static page, no Node toolchain.** The page is plain HTML, CSS and JavaScript served by the same Python server, with the LiveKit browser client pinned to an exact version. A Node build would add a second toolchain, a lockfile and its own CI job; for one screen that is cost without benefit. If the page outgrows this, that becomes a new ADR.

**A token endpoint, server-side secret.** The browser asks the server for a token. The server holds the LiveKit secret, mints a token that lives a few minutes, uses a fresh random room for each call, and puts the agent dispatch inside the token, so Emily joins when the caller does and greets a room that has someone in it. The server binds to 127.0.0.1 only.

**Live panel from the room itself.** The agent's state (listening, thinking, speaking) is already published by the framework. Transcriptions use the framework's own transcript stream. The gateway's events are sent on one custom topic, by an observer that does nothing when there is no room, so text tests and evals are unchanged.

**The review arrives after the call.** It runs once the session has closed, so it cannot travel over the room. The page fetches the call record by room name after hang-up and waits for it.

**Limits belong to the worker.** Every call has a length limit and there is a daily cap on calls. They are enforced in the worker, not in the page, so phone calls inherit them. (Before this ADR the plan listed them as standing constraints but the worker enforced neither; VERIFICATION says so.)

## Consequences

- Anyone with the repository and their own keys can run it; nobody else can use the owner's.
- The page proves nothing until a person completes a call in it. Server tests prove the token's grants, not the experience.
- A transcript shown to the caller includes the date of birth they spoke. The gateway's audit log never holds it, so the events panel does not either.
- The screenshot uses the mock patient only.
