#!/usr/bin/env python3
"""HW10 Part 4.3: p50 / p95 per stage and each stage's share of the cache-miss end-to-end latency, computed from the spans of the 50 measured requests."""
import json
import sys
from pathlib import Path

from tracing.spans import QUEUE_STAGES, trace_file
from tracing.store import by_trace, load_spans, percentile

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports/hw10/raw"
ROWS = [("Cache lookup", "cache_lookup"), ("Planner", "planner"), ("Writer", "writer"), ("Reviewer", "reviewer"), ("Queue wait (total)", "queue"), ("Evaluation", "evaluation")]


def stage_ms(spans: list[dict], stage: str) -> float | None:
    if stage == "queue":
        waits = [s["duration_ms"] for s in spans if s["stage"] in QUEUE_STAGES]
        return round(sum(waits), 2) if len(waits) == len(QUEUE_STAGES) else None
    hit = next((s for s in spans if s["stage"] == stage), None)
    return hit["duration_ms"] if hit else None


def main() -> int:
    spans_path = Path(sys.argv[1]) if len(sys.argv) > 1 else trace_file()
    data = json.loads((RAW / "latency_requests.json").read_text())
    traces = by_trace(load_spans(spans_path))
    miss_ids = [m["trace_id"] for m in data["misses"]]
    assert all(t in traces for t in miss_ids), "spans are missing for some of the 50 requests"
    per, share, e2e, accounted = {k: [] for _, k in ROWS}, {k: [] for _, k in ROWS}, [], []
    for tid in miss_ids:
        sp = traces[tid]
        total = stage_ms(sp, "request")
        e2e.append(total)
        used = 0.0
        for _, key in ROWS:
            value = stage_ms(sp, key)
            if value is not None:
                per[key].append(value)
                share[key].append(100 * value / total)
                if key != "evaluation":
                    used += value
        used += stage_ms(sp, "cache_store") or 0.0
        accounted.append(100 * used / total)
    table = []
    print(f"{len(miss_ids)} confirmed cache-miss requests (none served from the cache: {not any(m['is_cached'] for m in data['misses'])}); spans from {spans_path}")
    print(f"{'Stage':22} {'n':>3} {'p50 (ms)':>10} {'p95 (ms)':>10} {'% of cache-miss end-to-end (mean of per-request shares)':>56}")
    for label, key in ROWS:
        row = {"stage": label, "n": len(per[key]), "p50_ms": round(percentile(per[key], 50), 1), "p95_ms": round(percentile(per[key], 95), 1),
               "share_pct": round(sum(share[key]) / len(share[key]), 1), "share_of_median_pct": round(100 * percentile(per[key], 50) / percentile(e2e, 50), 1)}
        table.append(row)
        print(f"{label:22} {row['n']:>3} {row['p50_ms']:>10.1f} {row['p95_ms']:>10.1f} {row['share_pct']:>56.1f}")
    print(f"{'End-to-end (request)':22} {len(e2e):>3} {percentile(e2e, 50):>10.1f} {percentile(e2e, 95):>10.1f} {100.0:>56.1f}")
    other = round(100 - sum(accounted) / len(accounted), 1)
    print(f"request-path stages (cache lookup, planner, writer, reviewer, queue wait, cache store) account for {100 - other:.1f}% of the end-to-end time; the rest is {other:.1f}% other "
          "(HTTP handling, JSON, the ingress's own bookkeeping). Evaluation runs after the answer is returned, in the evaluator process, so it is not part of the request path.")
    request_path = [r for r in table if r["stage"] != "Evaluation"]
    dominant = max(request_path, key=lambda r: r["share_pct"])
    print(f"dominant contributor: {dominant['stage']} ({dominant['share_pct']}% of the end-to-end time, p50 {dominant['p50_ms']} ms)")
    hits = [h["latency_ms"] for h in data["hits"] if h["is_cached"]]
    hit_spans = [next((s["duration_ms"] for s in traces[h["trace_id"]] if s["stage"] == "request"), None) for h in data["hits"] if h["trace_id"] in traces and h["is_cached"]]
    hit_spans = [x for x in hit_spans if x is not None]
    print(f"cache-hit latency ({len(hit_spans)} hits, request spans): p50 {percentile(hit_spans, 50):.1f} ms, p95 {percentile(hit_spans, 95):.1f} ms")
    result = {"requests": len(miss_ids), "table": table, "end_to_end": {"p50_ms": round(percentile(e2e, 50), 1), "p95_ms": round(percentile(e2e, 95), 1), "mean_ms": round(sum(e2e) / len(e2e), 1)},
              "other_pct": other, "dominant": dominant, "cache_hit": {"n": len(hit_spans), "p50_ms": round(percentile(hit_spans, 50), 1), "p95_ms": round(percentile(hit_spans, 95), 1),
                                                                      "client_p50_ms": round(percentile(hits, 50), 1)},
              "max_similarity_of_misses": max(m["similarity"] or 0 for m in data["misses"]), "spans_file": str(spans_path)}
    (RAW / "latency_table.json").write_text(json.dumps(result, indent=2))
    print("saved reports/hw10/raw/latency_table.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
