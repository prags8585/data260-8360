#!/usr/bin/env python3
"""Builds reports/hw10/RUN_LOG.txt from the real console captures in reports/hw10/raw/console/."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CON = ROOT / "reports/hw10/raw/console"
PARTS = [
    ("10_stack.txt", "docker ps / process list", "Setup - containers, agents, ingress and Ollama"),
    ("20_part2_requests.txt", "PYTHONPATH=. python scripts/hw10_part2_run.py", "Part 2 - eight test questions through the ingress, cache and Kafka pipeline"),
    ("21_part2_evaluator.txt", "python evaluator.py --once", "Part 2 - the evaluator joins plan, draft and final by correlation_id and scores them"),
    ("30_trace_examples.txt", "PYTHONPATH=. python scripts/hw10_trace_examples.py", "Part 4.2 - a cache-hit, a cache-miss and a failed request"),
    ("31_trace_spans.txt", "PYTHONPATH=. python scripts/hw10_show_trace.py <trace_id>", "Part 4.2 - the spans of the three required traces"),
    ("40_latency_requests.txt", "PYTHONPATH=. python scripts/hw10_latency_experiment.py", "Part 4.3 - 50 confirmed cache-miss requests and 30 cache hits"),
    ("41_latency_evaluator.txt", "python evaluator.py --once", "Part 4.3 - the evaluation stage for the 50 requests"),
    ("42_latency_report.txt", "PYTHONPATH=. python scripts/hw10_latency_report.py", "Part 4.3 - p50 / p95 per stage from the spans"),
    ("50_judge_commit_proof.txt", "git log / status for eval_cases.json and human_labels.csv", "Part 3.1 - the frozen files were committed before the judge ran"),
    ("51_judge_validation.txt", "PYTHONPATH=. python scripts/hw10_judge_validation.py --sampling-check", "Part 3.2 / 3.3 - judge vs human labels, and repeatability"),
    ("60_tests_and_verify.txt", "python tests_hw10.py && PYTHONPATH=. python verify_hw10.py", "Offline tests and the live smoke test (writes reports/hw10/verification.json)"),
]


def main() -> None:
    out = ["# RUN_LOG.txt - DATA-260 Homework 10 (Karthik Pragada, SID4 8360, PORT_BASE 8260)",
           "# Real console output captured on a MacBook Air (Apple M4): Kafka 3.8.0, Redis Stack 7.4, MySQL, the HW8 agents, the HW9 ingress and cache; Ollama qwen3:8b (also the judge).",
           "# Agent/evaluator log lines are in UTC (the trailing Z); the '=== date ===' headers are local time. Each block was produced by the command shown above it.", ""]
    for name, cmd, title in PARTS:
        f = CON / name
        if f.exists():
            out += ["=" * 100, f"## {title}", f"$ {cmd}", "=" * 100, f.read_text().rstrip("\n"), ""]
    (ROOT / "reports/hw10/RUN_LOG.txt").write_text("\n".join(out))
    print("RUN_LOG lines:", len(out))


if __name__ == "__main__":
    main()
