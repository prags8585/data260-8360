"""Structured JSON spans, one line per stage, appended to one JSONL file (kafka_state/traces/spans.jsonl by default).

trace_id IS the HW8 correlation_id: no second request identifier exists. A request that is answered from the semantic cache
never enters Kafka, so the ingress mints its id the same way the HW8 client does (a uuid4) and uses it for the cache_lookup and request spans.

Span fields: trace_id, span_id, stage, start (UTC ISO, ms), end, start_ts / end_ts (epoch seconds), duration_ms, status ('ok' | 'error'),
error (text or null), service, plus stage specific attributes. Several processes append to the same file: each span is written with one
os.write on an O_APPEND descriptor, which does not interleave. Tracing must never break the pipeline, so every failure here is swallowed."""
import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = ROOT / "kafka_state/traces/spans.jsonl"

# the stages, in the order a request passes through them (the queue_* spans are the time a message waited in a Kafka topic)
STAGES = ["request", "cache_lookup", "agent_round_trip", "queue_inbox", "planner", "queue_tasks", "writer", "queue_drafts", "reviewer",
          "queue_final", "cache_store", "evaluation"]
QUEUE_STAGES = ["queue_inbox", "queue_tasks", "queue_drafts", "queue_final"]


def trace_file() -> Path:
    return Path(os.environ.get("TRACE_FILE", DEFAULT_FILE))


def iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts)) + f".{int(ts * 1000) % 1000:03d}Z"


def first_line(text: str, limit: int = 300) -> str:
    """Error texts (SQLAlchemy adds a second 'Background on this error' line) are kept to one line."""
    return (text.splitlines() or [""])[0][:limit]


def emit_span(trace_id: str | None, stage: str, start: float, end: float, status: str = "ok", error: str | None = None, service: str | None = None,
              **attrs) -> dict | None:
    """Writes one span; returns it (or None when there is no trace_id or the file cannot be written)."""
    if not trace_id:
        return None
    span = {"trace_id": trace_id, "span_id": uuid.uuid4().hex[:12], "stage": stage, "start": iso(start), "end": iso(end),
            "start_ts": round(start, 6), "end_ts": round(end, 6), "duration_ms": round(max(end - start, 0.0) * 1000, 2),
            "status": status, "error": error, "service": service or stage, **attrs}
    try:
        path = trace_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(span, ensure_ascii=False) + "\n").encode())
        finally:
            os.close(fd)
    except OSError:
        return None
    return span


class SpanHandle:
    """Lets the code inside `with span(...)` add attributes or mark the span as failed without raising."""

    def __init__(self) -> None:
        self.attrs: dict = {}
        self.status, self.error = "ok", None

    def set(self, **attrs) -> None:
        self.attrs.update(attrs)

    def fail(self, error: str) -> None:
        self.status, self.error = "error", error


@contextmanager
def span(trace_id: str | None, stage: str, service: str | None = None, **attrs):
    handle = SpanHandle()
    handle.attrs.update(attrs)
    start = time.time()
    try:
        yield handle
    except Exception as exc:
        handle.fail(first_line(f"{type(exc).__name__}: {exc}"))
        raise
    finally:
        emit_span(trace_id, stage, start, time.time(), handle.status, handle.error, service, **handle.attrs)


def message_time(msg) -> float | None:
    """Producer timestamp of a Kafka message in epoch seconds (None when the message has none, e.g. a test double)."""
    try:
        kind, ms = msg.timestamp()
        return ms / 1000 if ms and ms > 0 else None
    except Exception:
        return None


def queue_span(trace_id: str | None, stage: str, msg, consumed_at: float, service: str | None = None) -> dict | None:
    """The time a message waited in a topic: from the moment it was produced to the moment its consumer started working on it."""
    produced = message_time(msg)
    if produced is None:
        return None
    topic = msg.topic() if hasattr(msg, "topic") else None
    return emit_span(trace_id, stage, produced, max(consumed_at, produced), service=service, topic=topic)
