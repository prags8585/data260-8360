"""Data access for the dashboard: plain functions over the span file and the evaluation files, so they can be tested without Streamlit.

Data sources (the pages print these):
  spans       kafka_state/traces/spans.jsonl (written live by the ingress, Planner, Writer, Reviewer and evaluator); when that file does not exist
              (for example on a fresh clone) the committed copy reports/hw10/raw/spans.jsonl is used.
  evaluations reports/hw10/raw/part2_evals.jsonl (Part 2) and reports/hw10/raw/judge_validation.json (Part 3)."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from tracing.spans import QUEUE_STAGES
from tracing.store import by_trace, failing_stage, percentile, trace_path

failing_span = failing_stage  # the span that explains a failed trace

ROOT = Path(__file__).resolve().parent.parent
LIVE_SPANS = ROOT / "kafka_state/traces/spans.jsonl"
COMMITTED_SPANS = ROOT / "reports/hw10/raw/spans.jsonl"
RAW = ROOT / "reports/hw10/raw"
WINDOWS = {"All spans in the file": None, "Last 24 hours": 24 * 3600, "Last 1 hour": 3600, "Last 15 minutes": 900}
STAGE_LABELS = {"cache_lookup": "Cache lookup", "planner": "Planner", "writer": "Writer", "reviewer": "Reviewer", "queue": "Queue wait (total)", "evaluation": "Evaluation"}


def spans_path() -> Path:
    override = os.environ.get("DASHBOARD_SPANS")
    if override:
        return Path(override)
    return LIVE_SPANS if LIVE_SPANS.exists() and LIVE_SPANS.stat().st_size > 0 else COMMITTED_SPANS


def utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def window_bounds(spans: list[dict], seconds: int | None) -> tuple[float, float]:
    """The window ends at the newest span in the file (so a saved file stays meaningful) and starts `seconds` earlier (or at the oldest span)."""
    if not spans:
        return 0.0, 0.0
    end = max(s["end_ts"] for s in spans)
    start = min(s["start_ts"] for s in spans) if seconds is None else end - seconds
    return start, end


def in_window(spans: list[dict], start: float, end: float) -> list[dict]:
    return [s for s in spans if start <= s["start_ts"] <= end]


def latency_stats(values: list[float]) -> dict:
    return {"n": len(values), "p50_ms": percentile(values, 50), "p95_ms": percentile(values, 95), "mean_ms": sum(values) / len(values) if values else None}


def summary_metrics(spans: list[dict]) -> dict:
    """Request count, cache hit / miss split, error rate and end-to-end latency, from the `request` spans the ingress writes (one per request)."""
    requests = [s for s in spans if s["stage"] == "request"]
    hits = [s for s in requests if s.get("path") == "cache_hit"]
    misses = [s for s in requests if s.get("path") == "cache_miss"]
    errors = [s for s in requests if s["status"] == "error"]
    rejected = [s for s in requests if s.get("review_status") == "rejected"]
    n = len(requests)
    return {"requests": n, "hits": len(hits), "misses": len(misses), "hit_rate": len(hits) / n if n else None, "errors": len(errors),
            "error_rate": len(errors) / n if n else None, "rejected": len(rejected),
            "latency_hit": latency_stats([s["duration_ms"] for s in hits]), "latency_miss": latency_stats([s["duration_ms"] for s in misses if s["status"] == "ok"]),
            "latency_all": latency_stats([s["duration_ms"] for s in requests])}


def stage_table(spans: list[dict]) -> list[dict]:
    """p50 / p95 per stage over the cache-miss requests in `spans` (queue wait = the four topic waits of one request added up)."""
    traces = by_trace(spans)
    miss_ids = [t for t, sp in traces.items() if any(s["stage"] == "request" and s.get("path") == "cache_miss" and s["status"] == "ok" for s in sp)]
    rows = []
    for key, label in STAGE_LABELS.items():
        values = []
        for tid in miss_ids:
            sp = traces[tid]
            if key == "queue":
                waits = [s["duration_ms"] for s in sp if s["stage"] in QUEUE_STAGES]
                if len(waits) == len(QUEUE_STAGES):
                    values.append(sum(waits))
            else:
                found = next((s["duration_ms"] for s in sp if s["stage"] == key), None)
                if found is not None:
                    values.append(found)
        stats = latency_stats(values)
        rows.append({"Stage": label, "Requests": stats["n"], "p50 (ms)": None if stats["p50_ms"] is None else round(stats["p50_ms"], 1),
                     "p95 (ms)": None if stats["p95_ms"] is None else round(stats["p95_ms"], 1)})
    return rows


def trace_index(spans: list[dict]) -> list[dict]:
    """One row per trace, newest first: path (cache_hit / cache_miss / failed), total time and the failing stage."""
    rows = []
    for tid, sp in by_trace(spans).items():
        root = next((s for s in sp if s["stage"] == "request"), None)
        bad = failing_stage(sp)
        rows.append({"trace_id": tid, "start": sp[0]["start"], "start_ts": sp[0]["start_ts"], "path": trace_path(sp), "has_request_span": root is not None,
                     "total_ms": root["duration_ms"] if root else None, "failing_stage": bad["stage"] if bad else None})
    return sorted(rows, key=lambda r: r["start_ts"], reverse=True)


def trace_spans(spans: list[dict], trace_id: str) -> list[dict]:
    return by_trace([s for s in spans if s["trace_id"] == trace_id]).get(trace_id, [])


def span_notes(s: dict) -> str:
    keys = ("hit", "similarity", "threshold", "plan_source", "review_status", "failed_checks", "attempts", "dead_lettered", "topic", "key", "judge_calls",
            "plan_quality", "writer_helpfulness", "final_answer_helpfulness")
    return ", ".join(f"{k}={s[k]}" for k in keys if k in s and s[k] not in (None, [], ""))


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def load_json(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def example_traces() -> dict:
    return load_json(RAW / "trace_examples.json") or {}


def evaluation_rows(evals: list[dict]) -> list[dict]:
    return [{"case": f"c{i:02d}", "question": r["question"], "trace_id": r["trace_id"], "Plan quality": r["plan_quality"]["score"],
             "Writer helpfulness": r["writer_helpfulness"]["score"], "Final answer helpfulness": r["final_answer_helpfulness"]["score"],
             "Final minus draft": r["final_vs_draft"]["difference"], "review status": r["final_answer_helpfulness"].get("review_status")}
            for i, r in enumerate(evals, 1)]


def coordination_summary(rows: list[dict], evals: list[dict]) -> list[str]:
    """Plain-language reading of the Part 2 scores, written from the numbers (so it cannot drift from them)."""
    if not rows:
        return ["No evaluation results yet: run `python evaluator.py --once` after some requests."]
    def mean(key):
        values = [r[key] for r in rows if r[key] is not None]
        return sum(values) / len(values) if values else float("nan")
    unchanged = sum(1 for e in evals if e["final_answer_helpfulness"].get("final_answer") == e["writer_helpfulness"].get("draft"))
    rejected = sum(1 for r in rows if r["review status"] != "approved")
    same_text_gap = [e["final_vs_draft"]["difference"] for e in evals if e["final_answer_helpfulness"].get("final_answer") == e["writer_helpfulness"].get("draft")
                     and e["final_vs_draft"]["difference"] not in (None, 0)]
    lines = [f"Mean scores over {len(rows)} requests: plan {mean('Plan quality'):.2f}, writer draft {mean('Writer helpfulness'):.2f}, final answer {mean('Final answer helpfulness'):.2f} (scale 1-5).",
             f"The Reviewer approved the draft unchanged in {unchanged} requests and rejected {rejected}: it gates, it does not rewrite, so the final answer is only as good as the draft.",
             ]
    means = {"plan": mean("Plan quality"), "writer draft": mean("Writer helpfulness"), "final answer": mean("Final answer helpfulness")}
    weakest = min(means, key=means.get)
    lines.append(f"The lowest-scoring stage is the {weakest} ({means[weakest]:.2f}). " + (
        "The judge finds the plans generic (they name the lookup, not the exact facts), yet the drafts are mostly accurate, so a vague plan did not stop the Writer."
        if weakest == "plan" and means["writer draft"] >= 4 else "That stage is where coordination breaks down first."))
    if same_text_gap:
        lines.append(f"In {len(same_text_gap)} requests the final answer is word for word the draft but received a different score ({', '.join(f'{d:+d}' for d in same_text_gap)}): "
                     "the judge is deterministic, so this comes from how the two criteria are worded, not from randomness, and it is as large as the biggest improvement the metric could report; Final-vs-Draft is not trustworthy on its own.")
    return lines
