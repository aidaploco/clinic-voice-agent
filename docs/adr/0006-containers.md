# ADR-0006: Run it in containers

Status: accepted, 2026-11-15. Pulled forward from Phase 7.

## Context

Running the project took Python and `uv`, Node, three terminals, a database, and the right working directory (a mistake about that cost an afternoon, VERIFICATION O21). A stranger cloning the repository, or the owner on a new machine, should need Docker and a `.env` file.

## Decision

**One image, two commands.** The worker and the page server are the same code, so they share an image; compose starts them with different commands, next to the existing Postgres. `docker compose up --build` brings up all three.

**Multi-stage build.** The browser page is built in a Node stage; only its output reaches the final image, so Node and its packages are not in it. The Python stage installs exactly what `uv.lock` says.

**Reproducible and small in trust.** Base images are pinned by digest as well as tag (a test checks this), and the application runs as a non-root user.

**Secrets never enter the image.** `.env` is excluded from the build (a test checks the exclusion list), and the keys arrive as environment variables when a container starts, from `env_file`. The database address is overridden to the compose network's `db`.

**Still local-only.** Inside its container the page server listens on all addresses, because it must; compose publishes its port on the host's `127.0.0.1` only (a test checks every published port). The server's own host-name and origin checks apply as before.

**CI builds the image and checks it** (non-root, no `.env`, the page is present, both entry points import without keys, the page answers) inside `ci-success`. Nothing is pushed anywhere.

## Consequences

- The image is about 520 MB, mostly Python dependencies (the LiveKit and speech libraries).
- `console` mode, which uses the computer's microphone, is not containerised.
- The container's clock is UTC, so "tomorrow" in an appointment and the day boundary of the daily cap follow UTC unless `TZ` is set and time-zone data is installed. Not handled yet (VERIFICATION O22).
- Running a worker natively and one in a container on the same LiveKit project shares calls between them; `AGENT_NAME` gives a second deployment its own name.
