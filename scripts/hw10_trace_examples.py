#!/usr/bin/env python3
"""HW10 Part 4.2: three required traces through the real system - a cache hit, a successful cache miss, and a failed request.

The failure is a real dependency outage, not a simulated message: the MySQL container is stopped, so the Writer (which reads the live catalogue from
s8360_rel) cannot build its facts. It retries three times and dead-letters the task, and the ingress gives up after --timeout seconds.
MySQL is started again afterwards."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports/hw10/raw"
HIT_QUESTION = "How many seats are available in DATA-260?"      # asked in Part 2, so it is in the cache
MISS_QUESTION = "Which instructor teaches DATA-230?"
FAIL_QUESTION = "How many seats are available in CS-146?"


def ask(base: str, question: str, **extra) -> dict:
    return requests.post(f"{base}/ask", json={"question": question, "threshold": 0.95, **extra}, timeout=300).json()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8260")
    parser.add_argument("--timeout", type=float, default=25.0)
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    out = {}

    hit = ask(args.base, HIT_QUESTION)
    print(f"1. cache hit   : is_cached={hit['is_cached']} similarity={hit['similarity']} latency={hit['latency_ms']} ms trace_id={hit['trace_id']}")
    out["cache_hit"] = {"trace_id": hit["trace_id"], "question": HIT_QUESTION, "result": {k: hit[k] for k in ("is_cached", "similarity", "latency_ms", "answer")}}

    miss = ask(args.base, MISS_QUESTION)
    print(f"2. cache miss  : is_cached={miss['is_cached']} status={miss['status']} latency={miss['latency_ms']} ms trace_id={miss['trace_id']}")
    out["cache_miss"] = {"trace_id": miss["trace_id"], "question": MISS_QUESTION, "result": {k: miss[k] for k in ("is_cached", "status", "latency_ms", "answer")}}

    print("3. failed trace: stopping s8360-mysql, then asking a new question (the Writer needs the live catalogue)")
    subprocess.run(["docker", "stop", "s8360-mysql"], check=True, capture_output=True)
    try:
        fail = ask(args.base, FAIL_QUESTION, timeout_s=args.timeout)
    finally:
        subprocess.run(["docker", "start", "s8360-mysql"], check=True, capture_output=True)
    print(f"   result: status={fail['status']} answer={fail['answer']} latency={fail['latency_ms']} ms trace_id={fail['trace_id']}")
    out["failed"] = {"trace_id": fail["trace_id"], "question": FAIL_QUESTION, "result": {k: fail[k] for k in ("is_cached", "status", "latency_ms", "answer")},
                     "cause": "s8360-mysql was stopped; the Writer could not read the live catalogue"}
    for _ in range(60):  # wait until MySQL accepts connections again
        probe = subprocess.run(["docker", "exec", "s8360-mysql", "mysqladmin", "-uroot", "-phw4pass", "ping"], capture_output=True, text=True)
        if "alive" in probe.stdout:
            break
        time.sleep(2)
    print("   s8360-mysql is back:", "alive" in probe.stdout)
    (RAW / "trace_examples.json").write_text(json.dumps(out, indent=2))
    print("saved reports/hw10/raw/trace_examples.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
