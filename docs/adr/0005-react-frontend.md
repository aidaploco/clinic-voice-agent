# ADR-0005: The browser page is React and TypeScript

Status: accepted, 2026-11-15. Replaces the "one static page, no Node toolchain" decision in [ADR-0004](0004-browser-ui.md); the rest of ADR-0004 stands.

## Context

ADR-0004 chose a single static page to avoid a second toolchain. The owner wants the front end built with current, widely used tools, as part of the project's purpose (it is also a portfolio piece). The page is the part of the project a visitor sees first, and a typed, tested component codebase is a stronger demonstration than one script.

## Decision

**React 19, TypeScript in strict mode, Vite, Vitest with Testing Library, ESLint.** The code is in `web/`. LiveKit's official React SDK (`@livekit/components-react`) provides the room connection, audio playback and the agent's state; two small hooks of our own handle the transcript stream and the gateway-event stream.

**Typed edges, pure core.** What the Python side sends is parsed, not trusted: `parse.ts` turns anything malformed into a null or a safe default (an unknown review verdict becomes "not run", never "pass"). Wording, transcript merging and record polling are pure functions with unit tests; components are tested for what a visitor sees, including that text from a call is rendered as text and never as markup (a test, and an ESLint rule against `innerHTML`).

**Served by the Python server.** `npm run build` writes `web/dist`, which `python -m clinic_voice_agent.web` serves, with the same token endpoint and localhost-only rule as before. In development, `npm run dev` serves the page on 127.0.0.1:5173 and forwards `/api` to the Python server.

**Supply chain.** Every dependency is pinned to an exact version, each at least two weeks old when chosen, with a committed lockfile. CI runs `npm ci` (which fails if the lockfile disagrees), type-check, lint, tests, the build, and an audit of what ships to the browser, failing on high severity. The `web` job is part of `ci-success`.

## Consequences

- A second toolchain: Node 22.13 or newer, a lockfile and a CI job. A stranger needs `npm ci && npm run build` once before the page is served; the server says so when the build is missing.
- jsdom (the test browser) is held at 29.1.1: 30 needs Node 24.15 or 22.22, newer than the 24.8 the owner's machine runs, and that was found from the owner's install warnings, not before.
- TypeScript is held at 6.0 because `typescript-eslint` supports versions below 6.1; newer is available and will be taken when the linter does.
- The bundle is about 780 kB (216 kB compressed), mostly the LiveKit SDK. Fine for a page run on one's own machine.
- `npm audit` reports one moderate advisory (denial of service in `minimatch`) reached only through `typescript-eslint`, a build-time tool that reads our own files. npm's suggested fix downgrades the linter across a breaking change, so it is not applied; it is recorded in VERIFICATION.
- The page is proven only when a person completes a call in it (VERIFICATION O17).
