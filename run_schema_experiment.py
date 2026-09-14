#!/usr/bin/env python3


import json
import statistics
from pathlib import Path

from agent_graph import run

CASES_DIR = Path("reports/hw02/cases")
RAW_DIR = Path("reports/hw02/raw")
CASES_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

FIXED_INPUT = {
    "title": "Cloud Computing and Distributed Systems",
    "content": (
        "This course explores cloud computing architectures, distributed storage "
        "systems, container orchestration with Kubernetes, and microservices design "
        "patterns. Students will deploy scalable applications using AWS and GCP, and "
        "learn about load balancing, auto-scaling, and fault-tolerant system design. "
        "Prerequisites: networking fundamentals and basic Linux administration."
    ),
}

ADVERSARIAL_INPUT = {
    "title": "Comprehensive Computer Science Survey",
    "content": (
        "This course covers ten major subfields in a single semester: computer "
        "networking, cybersecurity, applied cryptography, database systems, operating "
        "systems internals, compiler construction, algorithm design and analysis, "
        "machine learning, computer vision, and natural language processing, with "
        "weekly guest lectures from a different subfield each week and a comprehensive "
        "cumulative final covering all ten areas in equal depth."
    ),
}

MODEL = "qwen3:8b"
TEMPERATURE = 0.7


def classify(record):
    if record["abandoned"]:
        return "abandoned_at_ceiling"
    if record["retries"] == 0:
        return "valid_first_attempt"
    if record["retries"] == 1:
        return "valid_after_1_retry"
    return "valid_after_2plus_retries"


def run_batch(title, content, n, ceiling, label):
    records = []
    for i in range(1, n + 1):
        print(f"[{label}] run {i}/{n} (ceiling={ceiling})", flush=True)
        try:
            out = run(title, content, MODEL, TEMPERATURE, ceiling, force_issue=False, verbose=False)
            rec = {
                "run_index": i,
                "ceiling": ceiling,
                "retries": out["retries"],
                "abandoned": out["abandoned"],
                "turn_count": out["turn_count"],
                "latency_ms": round(out["latency_ms"], 1),
                "final_tags": out["result"]["tags"],
                "final_summary": out["result"]["summary"],
                "error": None,
            }
            rec["classification"] = classify(rec)
        except Exception as exc:
            rec = {
                "run_index": i, "ceiling": ceiling, "retries": None, "abandoned": None,
                "turn_count": None, "latency_ms": None, "final_tags": None,
                "final_summary": None, "classification": "error", "error": str(exc),
            }
        print(json.dumps(rec), flush=True)
        records.append(rec)
    return records


def save_raw(records, filename):
    path = RAW_DIR / filename
    path.write_text(json.dumps(records, indent=2))
    print(f"Saved {len(records)} records to {path}", flush=True)


def summarize(records, ceiling_label):
    valid = [r for r in records if r["classification"] != "error"]
    n = len(valid)
    completed = [r for r in valid if not r["abandoned"]]
    completion_rate = len(completed) / n if n else 0
    latencies = [r["latency_ms"] for r in valid if r["latency_ms"] is not None]
    mean_latency = statistics.mean(latencies) if latencies else None
    counts = {}
    for r in valid:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1
    return {
        "ceiling": ceiling_label,
        "n": n,
        "completion_rate": round(completion_rate, 3),
        "mean_latency_ms": round(mean_latency, 1) if mean_latency else None,
        "counts": counts,
    }


def main():
    input_path = CASES_DIR / "schema_input.json"
    if not input_path.exists():
        input_path.write_text(json.dumps(FIXED_INPUT, indent=2))
        print(f"Saved fixed input to {input_path}", flush=True)
    else:
        print(f"Using existing fixed input at {input_path}", flush=True)
    fixed = json.loads(input_path.read_text())

    print("\n" + "#" * 70, flush=True)
    print("# PART 4.3 -- 30 runs, classifying retry behavior (ceiling=6)", flush=True)
    print("#" * 70, flush=True)
    runs_30 = run_batch(fixed["title"], fixed["content"], 30, ceiling=6, label="30-run")
    save_raw(runs_30, "schema_30runs.json")
    summary_30 = summarize(runs_30, "6 (classification experiment)")
    print(json.dumps(summary_30, indent=2), flush=True)

    print("\n" + "#" * 70, flush=True)
    print("# PART 4.4 -- ceiling comparison: 20 runs @ ceiling=2, 20 @ ceiling=10", flush=True)
    print("#" * 70, flush=True)
    runs_ceiling2 = run_batch(fixed["title"], fixed["content"], 20, ceiling=2, label="ceiling=2")
    save_raw(runs_ceiling2, "ceiling_2_runs.json")
    summary_c2 = summarize(runs_ceiling2, 2)

    runs_ceiling10 = run_batch(fixed["title"], fixed["content"], 20, ceiling=10, label="ceiling=10")
    save_raw(runs_ceiling10, "ceiling_10_runs.json")
    summary_c10 = summarize(runs_ceiling10, 10)

    print(json.dumps({"ceiling_2": summary_c2, "ceiling_10": summary_c10}, indent=2), flush=True)

    print("\n" + "#" * 70, flush=True)
    print("# PART 4.5 -- adversarial input, 5 runs (ceiling=6)", flush=True)
    print("#" * 70, flush=True)
    adv_path = CASES_DIR / "adversarial_input.json"
    adv_path.write_text(json.dumps(ADVERSARIAL_INPUT, indent=2))
    runs_adv = run_batch(ADVERSARIAL_INPUT["title"], ADVERSARIAL_INPUT["content"], 5, ceiling=6, label="adversarial")
    save_raw(runs_adv, "adversarial_5runs.json")
    summary_adv = summarize(runs_adv, "6 (adversarial)")
    print(json.dumps(summary_adv, indent=2), flush=True)

    all_summary = {
        "schema_30runs": summary_30,
        "ceiling_2": summary_c2,
        "ceiling_10": summary_c10,
        "adversarial_5runs": summary_adv,
    }
    (RAW_DIR / "part4_summary.json").write_text(json.dumps(all_summary, indent=2))
    print("\nAll experiments complete. Summary saved to reports/hw02/raw/part4_summary.json", flush=True)


if __name__ == "__main__":
    main()
