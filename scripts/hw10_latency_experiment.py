#!/usr/bin/env python3
"""HW10 Part 4.3: the stage-latency experiment.

Phase A: 50 requests that are CONFIRMED cache misses. The questions are new (never asked before), they are sent with store=false so that none of them
         can become a cache entry for a later one, and every response is checked: a request that was served from the semantic cache is discarded and
         replaced by the next candidate question, so exactly 50 misses are measured.
Phase B: 30 cache hits (exact repeats of questions the cache holds), measured separately.
The stage durations are not measured here: they come from the spans that the services wrote (scripts/hw10_latency_report.py)."""
import argparse
import json
import random
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports/hw10/raw"
CODES = ["DATA-260", "DATA-245", "CS-157A", "DATA-230", "CS-146", "ENGR-200"]
DEPARTMENTS = ["Data Science", "Computer Science", "Engineering"]
INSTRUCTORS = ["Dr. Priya Nair", "Dr. Elena Rossi", "Dr. Marcus Lee", "Dr. Samuel Okafor"]
CODE_TEMPLATES = ["What is the department of {c}?", "Which instructor is assigned to {c}?", "What is the title of the course {c}?",
                  "Does {c} still have open seats, and how many?", "I want to enrol in {c}; how many places are left?"]
DEPARTMENT_TEMPLATES = ["How many courses does the {d} department offer?", "What is the total seat count of the {d} department?", "List every course offered by {d}."]
INSTRUCTOR_TEMPLATES = ["How many courses does {i} teach?", "What courses does {i} teach, and how many seats do they have in total?"]
GLOBAL = ["Which course has the most seats left?", "Which course has the least room left?", "Which department has the fewest available seats?",
          "How many courses are in the catalogue?", "How many seats are open across the whole catalogue?", "Which instructor teaches the most courses?"]


def candidates(seed: int = 8360) -> list[str]:
    pool = [t.format(c=c) for t in CODE_TEMPLATES for c in CODES] + [t.format(d=d) for t in DEPARTMENT_TEMPLATES for d in DEPARTMENTS] + \
           [t.format(i=i) for t in INSTRUCTOR_TEMPLATES for i in INSTRUCTORS] + GLOBAL
    random.Random(seed).shuffle(pool)
    return pool


def ask(base: str, question: str, **extra) -> dict:
    return requests.post(f"{base}/ask", json={"question": question, "threshold": 0.95, **extra}, timeout=300).json()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8260")
    parser.add_argument("--misses", type=int, default=50)
    parser.add_argument("--hits", type=int, default=30)
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    started = time.time()
    misses, discarded = [], []
    for question in candidates():
        if len(misses) >= args.misses:
            break
        r = ask(args.base, question, store=False)
        row = {"question": question, "trace_id": r["trace_id"], "is_cached": r["is_cached"], "similarity": r["similarity"], "status": r["status"], "latency_ms": r["latency_ms"]}
        (discarded if r["is_cached"] else misses).append(row)
        print(f"miss {len(misses):>2}/{args.misses} {'DISCARDED (cache hit)' if r['is_cached'] else r['status']:9} {r['latency_ms']:>8.0f} ms sim={r['similarity']} {question}")
    assert len(misses) == args.misses and not any(m["is_cached"] for m in misses), "not enough confirmed cache misses"
    hit_questions = [row["question"] for row in json.loads((RAW / "part2_requests.json").read_text()) if row["status"] == "approved"]
    hits = []
    for i in range(args.hits):
        r = ask(args.base, hit_questions[i % len(hit_questions)])
        hits.append({"question": r["question"], "trace_id": r["trace_id"], "is_cached": r["is_cached"], "similarity": r["similarity"], "latency_ms": r["latency_ms"]})
    print(f"phase B: {sum(h['is_cached'] for h in hits)}/{len(hits)} requests were cache hits; median {sorted(h['latency_ms'] for h in hits)[len(hits) // 2]} ms")
    (RAW / "latency_requests.json").write_text(json.dumps({"started": started, "threshold": 0.95, "misses": misses, "discarded_cache_hits": discarded, "hits": hits}, indent=2))
    print(f"saved reports/hw10/raw/latency_requests.json (started at epoch {started:.0f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
