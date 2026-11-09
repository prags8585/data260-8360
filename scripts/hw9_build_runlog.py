#!/usr/bin/env python3
"""Builds reports/hw09/RUN_LOG.txt from the real console captures in reports/hw09/raw/console/."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CON = ROOT / "reports/hw09/raw/console"
PARTS = [
    ("01_stack_up.txt", "docker compose -f docker-compose.cache.yml up -d", "Setup - Redis Stack (RediSearch vector index), Kafka and MySQL"),
    ("02_part1_counter.txt", "PYTHONPATH=. python scripts/hw9_part1_counter.py", "Part 1 - Redis view counter, synced to MySQL every 10th increment"),
    ("03_part2_cache_demo.txt", "PYTHONPATH=. python scripts/hw9_part2_cache_demo.py", "Part 2 - semantic cache at the ingress, 12 queries"),
    ("03b_ingress_log_excerpt.txt", "grep 'cache HIT|cache MISS' kafka_state/logs/api.log", "Part 2 - ingress log lines for the demo"),
    ("04a_cases_commit_proof.txt", "git log / sha256 for cache_cases.yaml", "Part 3.1 - the labeled cases were committed before the sweep"),
    ("04_threshold_sweep.txt", "PYTHONPATH=. python scripts/hw9_threshold_sweep.py", "Part 3.2 - threshold sweep over the 40 labeled cases"),
    ("05_sweep_analysis.txt", "PYTHONPATH=. python scripts/hw9_analyze_sweep.py", "Part 3.2-3.4 - results table, one false hit in full, cost model"),
    ("05b_false_hit_truth.txt", "mysql query for the false-hit pair", "Part 3.3 - what MySQL says the correct answer is"),
    ("06_stale_demo.txt", "PYTHONPATH=. python scripts/hw9_stale_demo.py", "Part 3.5 - stale answer after a MySQL update and invalidation by data version"),
    ("07_part4_mine.txt", "PYTHONPATH=. python scripts/hw9_part4_run.py mine", "Part 4 - baseline on training data; candidate lessons"),
    ("08_part4_validate.txt", "PYTHONPATH=. python scripts/hw9_part4_run.py validate", "Part 4 - validation gate for each candidate lesson"),
    ("09_part4_demo.txt", "PYTHONPATH=. python scripts/hw9_part4_run.py demo", "Part 4 - one revision sequence and one lesson reused"),
    ("10_part4_final.txt", "PYTHONPATH=. python scripts/hw9_part4_run.py final", "Part 4 - four variants on the test questions"),
    ("11_tests_and_verify.txt", "python tests_hw9.py && PYTHONPATH=. python verify_hw09.py", "Offline tests and the live smoke test (writes reports/hw09/verification.json)"),
]


def main() -> None:
    out = ["# RUN_LOG.txt - DATA-260 Homework 9 (Karthik Pragada, SID4 8360, PORT_BASE 8260)",
           "# Real console output captured on a MacBook Air (Apple M4): Redis Stack 7.4 (RediSearch 2.10), Kafka 3.8.0, MySQL and the HW8 agents; Ollama qwen3:8b.",
           "# Container/agent log lines are in UTC (the trailing Z); the '=== date ===' headers are local time. Each block was produced by the command shown above it.",
           "# Note: a first sweep run was discarded because the machine ran out of memory and agent calls timed out; its files are kept as *_run1_invalid.* in raw/.", ""]
    for name, cmd, title in PARTS:
        f = CON / name
        if f.exists():
            out += ["=" * 100, f"## {title}", f"$ {cmd}", "=" * 100, f.read_text().rstrip("\n"), ""]
    (ROOT / "reports/hw09/RUN_LOG.txt").write_text("\n".join(out))
    print("RUN_LOG lines:", len(out))


if __name__ == "__main__":
    main()
