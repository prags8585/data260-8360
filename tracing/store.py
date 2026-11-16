"""Reading spans back: grouping by trace, the request path (cache hit / cache miss / failed), and percentiles."""
import json
import math
from collections import defaultdict
from pathlib import Path

from tracing.spans import STAGES, trace_file

__all__ = ["load_spans", "by_trace", "ordered", "trace_path", "trace_summary", "failing_stage", "percentile"]


def load_spans(path: str | Path | None = None) -> list[dict]:
    """All spans of a JSONL file; a line that is not valid JSON (a half-written line) is skipped."""
    path = Path(path) if path else trace_file()
    if not path.exists():
        return []
    spans = []
    for line in path.read_text().splitlines():
        try:
            span = json.loads(line)
        except ValueError:
            continue
        if isinstance(span, dict) and span.get("trace_id") and span.get("stage"):
            spans.append(span)
    return spans


def by_trace(spans: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for s in spans:
        grouped[s["trace_id"]].append(s)
    return {k: ordered(v) for k, v in grouped.items()}


def ordered(spans: list[dict]) -> list[dict]:
    """Stage order of a request: by start time, ties broken by the position of the stage in the pipeline."""
    rank = {stage: i for i, stage in enumerate(STAGES)}
    return sorted(spans, key=lambda s: (s["start_ts"], rank.get(s["stage"], 99)))


def trace_path(spans: list[dict]) -> str:
    """'cache_hit', 'cache_miss' or 'failed': failed means any span has status error, or the request never produced an answer."""
    if any(s["status"] == "error" for s in spans):
        return "failed"
    lookup = next((s for s in spans if s["stage"] == "cache_lookup"), None)
    if lookup is not None:
        return "cache_hit" if lookup.get("hit") else "cache_miss"
    return "cache_miss" if any(s["stage"] in ("planner", "writer", "reviewer") for s in spans) else "unknown"


# these two spans fail only BECAUSE a later stage failed (the ingress waited in vain), so they are not the root cause
CONSEQUENCE_STAGES = ("request", "agent_round_trip")


def failing_stage(spans: list[dict]) -> dict | None:
    """The span that explains a failed trace: the first stage that reports an error; the request/agent_round_trip spans only when nothing else does."""
    failed = [s for s in spans if s["status"] == "error"]
    root_cause = [s for s in failed if s["stage"] not in CONSEQUENCE_STAGES]
    return (root_cause or failed or [None])[0]


def trace_summary(spans: list[dict]) -> dict:
    root = next((s for s in spans if s["stage"] == "request"), None)
    bad = failing_stage(spans)
    return {"trace_id": spans[0]["trace_id"], "path": trace_path(spans), "stages": [s["stage"] for s in spans],
            "total_ms": root["duration_ms"] if root else round((max(s["end_ts"] for s in spans) - min(s["start_ts"] for s in spans)) * 1000, 2),
            "failing_stage": bad["stage"] if bad else None, "error": bad["error"] if bad else None, "start": spans[0]["start"]}


def percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolation percentile (q in 0-100), the same definition as numpy's default."""
    if not values:
        return None
    xs = sorted(values)
    k = (len(xs) - 1) * q / 100
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)
