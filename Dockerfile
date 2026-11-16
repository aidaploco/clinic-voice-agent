# One image for both processes: the worker (takes the calls) and the page server.
#
#   docker build -t clinic-voice-agent .
#   docker compose up            # db, worker and page at http://127.0.0.1:8765
#
# Secrets are never baked in: .env is excluded from the build (.dockerignore) and the keys
# arrive as environment variables when a container starts.

# Stage 1: build the browser page. Node and its packages stay in this stage and out of the image.
FROM node:24.8.0-slim@sha256:cadbfafeb6baf87eaaffa40b3640209c4b7fd38cebde65059d15bc39cd636b85 AS page
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: the Python application, at exactly the versions in uv.lock.
FROM python:3.13.5-slim-bookworm@sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419 AS app
COPY --from=ghcr.io/astral-sh/uv:0.7.21@sha256:a64333b61f96312df88eafce95121b017cbff72033ab2dbc6398edb4f24a75dd /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies first, so a change to the code does not reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src/ src/
# An editable install: the code stays under /app/src, which is what the default folders
# (recordings, the built page) are anchored to.
RUN uv sync --locked --no-dev
COPY --from=page /web/dist web/dist

# Not root. The recordings folder is the only place the application writes.
RUN useradd --create-home --uid 1000 app && mkdir recordings && chown app:app recordings
USER app
ENV PATH="/app/.venv/bin:$PATH"

# The worker by default; compose.yaml runs the page server from the same image.
CMD ["python", "-m", "clinic_voice_agent.worker", "start"]
