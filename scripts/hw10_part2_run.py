#!/usr/bin/env python3
"""HW10 Part 2: sends the test questions through the real system (ingress -> cache -> Planner -> Writer -> Reviewer) and prints the trace ids;
`evaluator.py --once` then scores them. The questions are fixed here so the run can be repeated. The cache threshold is 0.95, the value chosen in the HW9 sweep."""
import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports/hw10/raw"
QUESTIONS = [
    "How many seats are available in DATA-260?",
    "Who teaches Web Programming?",
    "How many seats do the Computer Science courses offer in total?",
    "Which course has the most available seats?",
    "How many courses does Dr. Marcus Lee teach?",
    "Which department has the most available seats, and which course there has the most seats?",
    "List the courses in the Data Science department.",
    "What time does DATA-260 meet?",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8260")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, q in enumerate(QUESTIONS, 1):
        r = requests.post(f"{args.base}/ask", json={"question": q, "threshold": 0.95}, timeout=300).json()
        rows.append({"case": f"c{i:02d}", "question": q, "trace_id": r["trace_id"], "is_cached": r["is_cached"], "status": r["status"], "answer": r["answer"],
                     "latency_ms": r["latency_ms"]})
        print(f"c{i:02d} {'HIT ' if r['is_cached'] else 'MISS'} {r['status']:9} {r['latency_ms']:>8.0f} ms trace_id={r['trace_id']}")
        print(f"     Q: {q}\n     A: {r['answer']}")
    (RAW / "part2_requests.json").write_text(json.dumps(rows, indent=2))
    print(f"saved {len(rows)} requests to reports/hw10/raw/part2_requests.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
