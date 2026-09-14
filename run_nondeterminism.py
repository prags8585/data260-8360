#!/usr/bin/env python3
import argparse
import json
from collections import Counter
from pathlib import Path

from agents_demo import run_pipeline

INPUT_PATH = Path("reports/hw01/cases/nondeterminism_input.json")
RAW_DIR = Path("reports/hw01/raw")


def percentile(data, pct):
    if not data:
        return None
    data = sorted(data)
    k = (len(data) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(data) - 1)
    if f == c:
        return data[f]
    return data[f] + (data[c] - data[f]) * (k - f)


def run_sweep(runs_per_temp, temperatures, model):
    with open(INPUT_PATH) as f:
        case = json.load(f)
    title, content = case["title"], case["content"]

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    all_results = []
    total_calls = runs_per_temp * len(temperatures)
    call_num = 0

    for temperature in temperatures:
        print(f"\n{'#' * 70}\n# TEMPERATURE {temperature} -- {runs_per_temp} runs\n{'#' * 70}")
        for i in range(1, runs_per_temp + 1):
            call_num += 1
            print(f"\n--- run {i}/{runs_per_temp} @ temp={temperature}  (overall {call_num}/{total_calls}) ---")
            try:
                result = run_pipeline(title, content, model, temperature, verbose=False)
                final = result["final"]
                record = {
                    "run_index": i,
                    "temperature": temperature,
                    "tags": final["tags"],
                    "summary": final["summary"],
                    "reviewer_changed": result["reviewer_changed"],
                    "planner_latency_ms": round(result["planner_latency_ms"], 1),
                    "reviewer_latency_ms": round(result["reviewer_latency_ms"], 1),
                    "total_latency_ms": round(result["total_latency_ms"], 1),
                    "error": None,
                }
            except Exception as exc:
                record = {
                    "run_index": i,
                    "temperature": temperature,
                    "tags": None,
                    "summary": None,
                    "reviewer_changed": None,
                    "planner_latency_ms": None,
                    "reviewer_latency_ms": None,
                    "total_latency_ms": None,
                    "error": str(exc),
                }
            all_results.append(record)
            print(json.dumps(record, indent=2))

    json_path = RAW_DIR / "nondeterminism_runs.json"
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2)

    csv_path = RAW_DIR / "nondeterminism_runs.csv"
    with open(csv_path, "w") as f:
        f.write(
            "run_index,temperature,tags,summary,reviewer_changed,"
            "planner_latency_ms,reviewer_latency_ms,total_latency_ms,error\n"
        )
        for r in all_results:
            tags_str = "|".join(r["tags"]) if r["tags"] else ""
            summary_escaped = (r["summary"] or "").replace('"', '""')
            error_escaped = (r["error"] or "").replace('"', '""')
            f.write(
                f'{r["run_index"]},{r["temperature"]},"{tags_str}","{summary_escaped}",'
                f'{r["reviewer_changed"]},{r["planner_latency_ms"]},{r["reviewer_latency_ms"]},'
                f'{r["total_latency_ms"]},"{error_escaped}"\n'
            )

    print(f"\nSaved {len(all_results)} raw records to {json_path} and {csv_path}")

    print(f"\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    summary_stats = {}
    for temperature in temperatures:
        subset = [r for r in all_results if r["temperature"] == temperature and r["error"] is None]
        failed = [r for r in all_results if r["temperature"] == temperature and r["error"] is not None]
        n = len(subset)

        tag_sets = [tuple(sorted(r["tags"])) for r in subset]
        distinct_sets = len(set(tag_sets))

        tag_counts = Counter()
        for r in subset:
            for t in set(r["tags"]):
                tag_counts[t] += 1
        tags_in_all = sorted([t for t, c in tag_counts.items() if c == n]) if n else []
        tags_in_exactly_one = sorted([t for t, c in tag_counts.items() if c == 1])

        latencies = [r["total_latency_ms"] for r in subset]
        p50 = percentile(latencies, 50)
        p95 = percentile(latencies, 95)
        p99 = percentile(latencies, 99)

        stats = {
            "successful_runs": n,
            "failed_runs": len(failed),
            "distinct_tag_sets": distinct_sets,
            "tags_in_all_runs": tags_in_all,
            "tags_in_exactly_one_run": tags_in_exactly_one,
            "latency_p50_ms": round(p50, 1) if p50 is not None else None,
            "latency_p95_ms": round(p95, 1) if p95 is not None else None,
            "latency_p99_ms": round(p99, 1) if p99 is not None else None,
        }
        summary_stats[str(temperature)] = stats

        print(f"\n--- Temperature {temperature} ({n} successful / {len(failed)} failed) ---")
        print(json.dumps(stats, indent=2))

    summary_path = RAW_DIR / "nondeterminism_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary_stats, f, indent=2)
    print(f"\nSaved summary to {summary_path}")


def main():
    parser = argparse.ArgumentParser(description="Non-determinism sweep over agents_demo.py.")
    parser.add_argument("--runs", type=int, default=20, help="Runs per temperature (default 20)")
    parser.add_argument("--temperatures", type=str, default="0.7,0.0")
    parser.add_argument("--model", type=str, default="qwen3:8b")
    args = parser.parse_args()

    temperatures = [float(t) for t in args.temperatures.split(",")]
    run_sweep(args.runs, temperatures, args.model)


if __name__ == "__main__":
    main()
