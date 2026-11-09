#!/usr/bin/env python3
"""HW9 Part 3.2: fill the cache with the 10 seed queries, then run the 40 labeled cases at each threshold.

Every miss runs the real Planner -> Writer -> Reviewer pipeline over Kafka, so the latencies are measured, not modeled.
The cache is read-only during the sweep (misses are not stored), so every threshold sees the same cache."""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

from cache_svc.agent_client import AgentClient
from cache_svc.cost_model import COST_FALSE_HIT, COST_HIT, COST_MISS, total_cost
from cache_svc.course_db import CourseDB
from cache_svc.embedding import embed
from cache_svc.ingress import QAIngress
from cache_svc.semantic_cache import SemanticCache
from kafka_svc.bus import setup_logging

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports/hw09/raw/threshold_sweep.json"
THRESHOLDS = [0.75, 0.80, 0.85, 0.90, 0.95]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thresholds", type=float, nargs="*", default=THRESHOLDS)
    args = parser.parse_args()
    setup_logging()

    cases_file = ROOT / "cache_cases.yaml"
    spec = yaml.safe_load(cases_file.read_text())
    sha = hashlib.sha256(cases_file.read_bytes()).hexdigest()
    commit = subprocess.run(["git", "log", "-1", "--format=%H %cd", "--date=iso", "--", "cache_cases.yaml"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    print(f"=== {datetime.now():%Y-%m-%d %H:%M:%S} === Part 3 threshold sweep")
    print(f"cache_cases.yaml sha256 {sha[:16]}...; last commit touching it: {commit}")
    print(f"{len(spec['seed_queries'])} seed queries, {len(spec['cases'])} cases, thresholds {args.thresholds}")

    cache, db, agent = SemanticCache(), CourseDB(), AgentClient()
    cache.ensure_index()
    for _ in range(3):
        embed(["warm-up", "How many seats are available in DATA-260?"])
    ingress = QAIngress(cache, db, agent.ask)

    print(f"\n-- seeding the cache (flushed {cache.flush()} old entries); each seed is answered by the real agent pipeline")
    seeds = {}
    for seed in spec["seed_queries"]:
        r = ingress.ask(seed["query"], threshold=2.0, track=False)  # threshold 2.0 can never hit, so the answer comes from the pipeline
        if r["status"] != "approved" or not r["cache_key"]:
            print(f"!! seed {seed['id']} was not approved: {r}")
            return 1
        seeds[seed["id"]] = {"query": seed["query"], "answer": r["answer"], "cache_key": r["cache_key"], "pipeline_ms": r["latency_ms"]}
        print(f"  {seed['id']}: {seed['query']}  ->  {r['answer']}")

    by_query = {s["query"]: sid for sid, s in seeds.items()}
    report = {"cache_cases_sha256": sha, "cache_cases_commit": commit, "started": datetime.now().isoformat(timespec="seconds"),
              "seeds": seeds, "costs": {"miss": COST_MISS, "hit": COST_HIT, "false_hit": COST_FALSE_HIT}, "thresholds": {}}
    for t in args.thresholds:
        print(f"\n-- threshold {t:.2f}")
        rows = []
        for case in spec["cases"]:
            r = ingress.ask(case["query"], threshold=t, store=False, track=False)
            matched = by_query.get(r["cached_query"]) if r["is_cached"] else None
            wrong = r["is_cached"] and (not case["expected_hit"] or matched != case.get("cached_seed"))
            rows.append({"id": case["id"], "category": case["category"], "query": case["query"], "expected_hit": case["expected_hit"],
                         "is_cached": r["is_cached"], "similarity": r["similarity"], "nearest_seed": by_query.get(r["cached_query"]),
                         "matched_seed": matched, "false_hit": bool(wrong), "missed_hit": (not r["is_cached"]) and case["expected_hit"],
                         "latency_ms": r["latency_ms"], "answer": r["answer"], "status": r["status"]})
            print(f"  {case['id']} {'HIT ' if r['is_cached'] else 'MISS'} sim={r['similarity']:.4f} {r['latency_ms']:>8.1f} ms {'FALSE HIT' if wrong else ''}")
        hits = sum(x["is_cached"] for x in rows)
        false_hits = sum(x["false_hit"] for x in rows)
        should_miss = sum(not x["expected_hit"] for x in rows)
        summary = {"hits": hits, "misses": len(rows) - hits, "false_hits": false_hits, "should_miss_cases": should_miss,
                   "hit_rate": round(hits / len(rows), 4), "false_hit_rate": round(false_hits / should_miss, 4),
                   "mean_latency_ms": round(sum(x["latency_ms"] for x in rows) / len(rows), 1),
                   "mean_latency_ms_hit": round(sum(x["latency_ms"] for x in rows if x["is_cached"]) / hits, 1) if hits else None,
                   "mean_latency_ms_miss": round(sum(x["latency_ms"] for x in rows if not x["is_cached"]) / (len(rows) - hits), 1) if hits < len(rows) else None,
                   "total_cost": total_cost(hits, len(rows) - hits, false_hits)}
        report["thresholds"][f"{t:.2f}"] = {"summary": summary, "cases": rows}
        print(f"  => {summary}")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2))  # saved after every threshold, so a long run is never lost
    report["finished"] = datetime.now().isoformat(timespec="seconds")
    OUT.write_text(json.dumps(report, indent=2))
    print(f"\nsaved {OUT.relative_to(ROOT)}")
    agent.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
