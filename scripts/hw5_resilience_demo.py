#!/usr/bin/env python3
"""HW5 Part 3: (a) the three retry scenarios and (b) the 150-call fault-injection
experiment (0% / 20% / 50% injected failure rates x 50 calls, seeded by VERIFY_SEED).

Faults are injected into the REAL MySQL-backed repository: before each storage
attempt a seeded RNG decides whether to raise a TransientError. The RNG is
re-seeded with VERIFY_SEED for every rate, so the same seed reproduces the exact
same success/failure sequence on every run (checked below by running it twice).

Writes reports/hw05/raw/fault_injection_calls.{json,csv} and fault_injection_summary.json.
Usage: python scripts/hw5_resilience_demo.py
"""

import csv
import json
import logging
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import domain_tools as dt  # noqa: E402
from resilience import INTERACTIVE, AttemptLog, TransientError  # noqa: E402

VERIFY_SEED = 260000 + 8360
RATES = [0.0, 0.2, 0.5]
CALLS_PER_RATE = 50
RAW = ROOT / "reports/hw05/raw"
RAW.mkdir(parents=True, exist_ok=True)


class FaultyRepo:
    """Wraps a real repo; each attempt may fail with an injected, seeded fault."""

    def __init__(self, inner, rate: float, seed: int):
        self.inner, self.rate, self.rng = inner, rate, random.Random(seed)
        self.injected = 0

    def _maybe_fail(self):
        if self.rng.random() < self.rate:
            self.injected += 1
            raise TransientError("injected fault")

    def search(self, query, limit):
        self._maybe_fail()
        return self.inner.search(query, limit)

    def get(self, course_id):
        self._maybe_fail()
        return self.inner.get(course_id)

    def stats(self, group_by):
        self._maybe_fail()
        return self.inner.stats(group_by)


class ScriptedRepo:
    """Fails the first `fail_times` attempts, then succeeds -- for the demo."""

    def __init__(self, fail_times: int):
        self.fail_times, self.attempts = fail_times, 0

    def search(self, query, limit):
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise TransientError(f"connection reset (attempt {self.attempts})")
        return [{"id": 3, "courseCode": "CS-157A", "courseTitle": "Database Systems"}]

    def get(self, course_id): raise NotImplementedError
    def stats(self, group_by): raise NotImplementedError


def demo(label: str, fail_times: int):
    trace = AttemptLog()
    repo = dt.ResilientRepo(ScriptedRepo(fail_times), INTERACTIVE, trace=trace)
    print(f"\n--- {label} ---", flush=True)
    start = time.perf_counter()
    result = dt.search_courses(repo, "database", 5)
    ms = (time.perf_counter() - start) * 1000
    print(f"attempts made : {trace.attempts}  ({', '.join(e['outcome'] for e in trace.events)})")
    print(f"envelope      : {json.dumps(result)[:150]}")
    print(f"elapsed       : {ms:.1f} ms")
    return {"scenario": label, "attempts": trace.attempts, "ok": result["ok"], "error": result["error"], "elapsed_ms": round(ms, 1)}


def run_rate(rate: float):
    real = dt.SqlCourseRepo()
    real.search("data", 1)      # uncounted warm-up: first call pays connection-pool / ORM start-up cost
    faulty = FaultyRepo(real, rate, VERIFY_SEED)
    out, trace = [], AttemptLog()
    repo = dt.ResilientRepo(faulty, INTERACTIVE, trace=trace)
    plan = [lambda: dt.search_courses(repo, "data", 5), lambda: dt.course_detail(repo, 1), lambda: dt.course_stats(repo, "department")]
    names = ["search_courses", "course_detail", "course_stats"]
    for i in range(CALLS_PER_RATE):
        trace.attempts, trace.events = 0, []
        start = time.perf_counter()
        result = plan[i % 3]()
        ms = (time.perf_counter() - start) * 1000
        out.append({"failure_rate": rate, "call": i + 1, "tool": names[i % 3], "attempts": trace.attempts,
                    "ok": result["ok"], "error": result["error"], "latency_ms": round(ms, 3)})
    return out, faulty.injected


def pct99(values):
    v = sorted(values)
    k = (len(v) - 1) * 0.99
    f, c = int(k), min(int(k) + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.WARNING, format="  [retry log] %(message)s", force=True)
    print(f"=== {time.strftime('%Y-%m-%d %H:%M:%S %Z')} ===  VERIFY_SEED={VERIFY_SEED}  policy={INTERACTIVE}")
    demos = [demo("1. success on the first attempt", 0),
             demo("2. failure on the first attempt, success after a retry", 1),
             demo("3. failure after all allowed retries -> clean error result", 99)]
    (RAW / "retry_demo.json").write_text(json.dumps(demos, indent=2))

    logging.disable(logging.CRITICAL)   # per-attempt log lines would flood the 150-call run
    print("\n=== fault-injection experiment: 3 rates x 50 calls ===")
    all_calls, summary, sequences = [], [], {}
    for rate in RATES:
        calls, injected = run_rate(rate)
        sequences[rate] = [(c["ok"], c["attempts"]) for c in calls]
        lat = [c["latency_ms"] for c in calls]
        ok_n = sum(c["ok"] for c in calls)
        row = {"injected_failure_rate": f"{int(rate * 100)}%", "calls": len(calls), "successes": ok_n,
               "success_rate_pct": round(100 * ok_n / len(calls), 1), "mean_latency_ms": round(statistics.mean(lat), 2),
               "p99_latency_ms": round(pct99(lat), 2), "faults_injected": injected,
               "retried_calls": sum(c["attempts"] > 1 for c in calls)}
        summary.append(row)
        all_calls += calls
        print(f"rate {row['injected_failure_rate']:>3}: success {ok_n}/{len(calls)} ({row['success_rate_pct']}%)  "
              f"mean {row['mean_latency_ms']} ms  p99 {row['p99_latency_ms']} ms  "
              f"faults injected {injected}  calls that retried {row['retried_calls']}")

    # reproducibility: same VERIFY_SEED must give the same sequence
    again = {rate: [(c["ok"], c["attempts"]) for c in run_rate(rate)[0]] for rate in RATES}
    reproducible = again == sequences
    print(f"\nreproducibility check (re-run with the same seed, compare ok/attempts sequence of all 150 calls): "
          f"{'IDENTICAL' if reproducible else 'DIFFERENT'}")

    (RAW / "fault_injection_calls.json").write_text(json.dumps(all_calls, indent=2))
    with open(RAW / "fault_injection_calls.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_calls[0]))
        w.writeheader(); w.writerows(all_calls)
    (RAW / "fault_injection_summary.json").write_text(json.dumps({"verify_seed": VERIFY_SEED, "policy": INTERACTIVE.__dict__,
                                                                  "reproducible": reproducible, "rows": summary}, indent=2))
    print(f"saved {len(all_calls)} call records -> {RAW}/fault_injection_calls.json / .csv")
    return 0 if reproducible and len(all_calls) == 150 else 1


if __name__ == "__main__":
    sys.exit(main())
