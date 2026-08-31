# METRICS.md — DATA-260 Homework 1

## Part 3 — Measuring Non-Determinism

**Fixed input** (`reports/hw01/cases/nondeterminism_input.json`):

- Title: *Data Structures and Algorithms*
- Content: *This course covers fundamental data structures including arrays, linked lists, stacks, queues, trees, and graphs, along with algorithm design techniques such as sorting, searching, divide-and-conquer, dynamic programming, and greedy methods. Students will analyze time and space complexity using Big-O notation and implement each structure from scratch in Python. Prerequisites: introductory programming and discrete mathematics.*

**Model:** `qwen3:8b` (Ollama, local) — **Command:** `python run_nondeterminism.py` — 20 runs at temperature 0.7, 20 runs at temperature 0.0 (40 runs total, 0 failures).

### Tag distribution

| Metric | Temp 0.7 | Temp 0.0 |
|---|---|---|
| Distinct tag sets | 11 (out of 20) | 1 (out of 20) |
| Tags in all 20 runs | *(none)* | "algorithm design techniques", "big o notation", "data structures implementation" |
| Tags in exactly 1 run | "algorithm analysis", "big o analysis", "big o notation", "big-o complexity analysis", "complexity analysis", "dynamic programming methods", "linked list implementation", "python programming", "time and space complexity" (9 tags) | *(none)* |

### Latency (milliseconds, full Planner+Reviewer pipeline per run)

| Metric | Temp 0.7 | Temp 0.0 |
|---|---|---|
| p50 | 77,272.4 | 118,949.2 |
| p95 | 102,800.5 | 135,981.1 |
| p99 | 111,202.8 | 138,073.8 |

### Raw data

Full per-run records (all 40 runs, tags + summary + latency): `reports/hw01/raw/nondeterminism_runs.json` and `reports/hw01/raw/nondeterminism_runs.csv`. Machine-computed summary: `reports/hw01/raw/nondeterminism_summary.json`.
