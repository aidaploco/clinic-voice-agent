"""Traces of a call, with the personal data left out.

A trace shows where a call's time went: each turn, the speech services, the model, every tool
call. It is the most useful thing to look at when a call feels slow, and by default it is also a
copy of the conversation. Here it is not:

- The framework's own filter strips what it knows to be personal (what was said, what the model
  said, tool arguments) before any exporter sees it: `allow_pii=False`.
- A second filter, ours, runs after it and takes out anything shaped like a phone number, an
  email address or a home-folder path from what is left, and drops any attribute named for a
  phone number, a room (a phone call's room is named for the caller's number) or a stack trace.

Spans go to an OpenTelemetry collector when `TRACE_ENDPOINT` is set (Phoenix, in
`docker compose --profile traces up`), and to a file as JSON lines when `TRACE_FILE` is set,
which is how the filters are checked against a real call. With neither, nothing is traced.
"""

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

SERVICE = "clinic-voice-agent"
PHONE = re.compile(r"\+?\d[\d\s().-]{7,17}\d")
EMAIL = re.compile(r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
HOME = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+")
DROP_KEYS = ("phone", "room", "participant", "identity", "sip.", "stack")
REDACTED = "[removed]"

_installed = False


def scrub_value(value: Any) -> Any:
    """A span attribute with phone-shaped and email-shaped text taken out."""
    if isinstance(value, str):
        return HOME.sub("/~", EMAIL.sub(REDACTED, PHONE.sub(REDACTED, value)))
    if isinstance(value, tuple | list):
        return type(value)(scrub_value(v) for v in value)
    return value


def scrub_attributes(attributes: dict[str, Any] | None) -> dict[str, Any]:
    return {
        key: scrub_value(value)
        for key, value in (attributes or {}).items()
        if not any(word in key.lower() for word in DROP_KEYS)
    }


class ScrubbingProcessor(SpanProcessor):
    """Rewrites a finished span's attributes (and its events') before the exporters see it.

    Registered after the framework's filter and before the exporting processors, so they all
    export what it leaves.
    """

    def on_end(self, span: ReadableSpan) -> None:
        span._attributes = scrub_attributes(dict(span.attributes or {}))  # type: ignore[attr-defined]  # noqa: SLF001
        for event in span.events:
            event._attributes = scrub_attributes(dict(event.attributes or {}))  # type: ignore[attr-defined]  # noqa: SLF001


class JsonLinesExporter(SpanExporter):
    """Spans to a file, one JSON object per line: for checking what a call would export."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with self._path.open("a") as out:
            for span in spans:
                out.write(json.dumps(json.loads(span.to_json()), ensure_ascii=False) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


def build_provider(endpoint: str | None, trace_file: Path | None) -> TracerProvider | None:
    if not endpoint and not trace_file:
        return None
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE}))
    provider.add_span_processor(ScrubbingProcessor())
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces"))
        )
    if trace_file:
        provider.add_span_processor(SimpleSpanProcessor(JsonLinesExporter(trace_file)))
    return provider


def setup(endpoint: str | None, trace_file: Path | None) -> bool:
    """Start tracing if it is asked for. Safe to call for every call: it sets up once."""
    global _installed  # noqa: PLW0603
    if _installed:
        return True
    provider = build_provider(endpoint, trace_file)
    if provider is None:
        return False
    from livekit.agents.telemetry import set_tracer_provider

    set_tracer_provider(provider, allow_pii=False)
    _installed = True
    return True
