#!/usr/bin/env python3
"""HW9 Part 2: 12 queries (exact duplicates, paraphrases, new questions) through POST /ask on the semantic-cache ingress."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parent.parent / "reports/hw09/raw/part2_demo.json"
QUERIES = [
    ("new", "How many seats are available in DATA-260?"),
    ("exact duplicate of #1", "How many seats are available in DATA-260?"),
    ("paraphrase of #1", "What is the seat availability for course DATA-260?"),
    ("new", "Who teaches CS-157A?"),
    ("paraphrase of #4", "Which instructor is teaching CS-157A?"),
    ("exact duplicate of #4", "Who teaches CS-157A?"),
    ("new", "Which department has the most available seats?"),
    ("paraphrase of #7", "Which department has the largest number of open seats?"),
    ("new, similar wording to #1", "How many seats are available in DATA-230?"),
    ("new, unrelated", "What is the capital of France?"),
    ("new", "How many courses does Dr. Marcus Lee teach?"),
    ("paraphrase of #11", "How many classes is Dr. Marcus Lee teaching?"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8260")
    parser.add_argument("--threshold", type=float, default=0.85)
    args = parser.parse_args()
    client = httpx.Client(base_url=args.base, timeout=300)

    print(f"=== {datetime.now():%Y-%m-%d %H:%M:%S} === Part 2 semantic cache, threshold {args.threshold}, {len(QUERIES)} queries")
    print(f"flushed the cache: {client.delete('/cache').json()}\n")
    results = []
    for n, (kind, question) in enumerate(QUERIES, 1):
        r = client.post("/ask", json={"question": question, "threshold": args.threshold}).json()
        results.append(r)
        sim = "  -  " if r["similarity"] is None else f"{r['similarity']:.4f}"
        answer = (r["answer"] or f"<{r['status']}>")
        print(f"#{n:<2} {'HIT ' if r['is_cached'] else 'MISS'} is_cached={str(r['is_cached']).lower():5} similarity={sim} latency={r['latency_ms']:>8.1f} ms  [{kind}]")
        print(f"      Q: {question}")
        print(f"      A: {answer}")
        if r["is_cached"] and r["cached_query"] != question:
            print(f"      served from the cached query: {r['cached_query']!r}")

    hits = [r for r in results if r["is_cached"]]
    misses = [r for r in results if not r["is_cached"]]
    mean = lambda rows: sum(r["latency_ms"] for r in rows) / len(rows) if rows else float("nan")  # noqa: E731
    print(f"\ncache hit rate: {len(hits)}/{len(results)} = {100 * len(hits) / len(results):.1f}%")
    print(f"average latency, served from cache: {mean(hits):.1f} ms ({len(hits)} queries)")
    print(f"average latency, agent pipeline:    {mean(misses):.1f} ms ({len(misses)} queries)")
    stats = client.get("/cache/stats").json()
    print(f"GET /cache/stats -> {stats}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"threshold": args.threshold, "queries": [{"kind": kind, **r} for (kind, _), r in zip(QUERIES, results, strict=True)],
                               "hit_rate": len(hits) / len(results), "avg_latency_ms_hit": mean(hits), "avg_latency_ms_miss": mean(misses), "stats": stats}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
