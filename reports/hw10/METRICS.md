# METRICS - DATA-260 Homework 10

Numbers come from the files in `reports/hw10/raw/` (one run each; model latencies vary from run to run).

## Configuration

| Value | Setting |
|---|---|
| SID4 / PORT_BASE / PREFIX / SEED / VERIFY_SEED | 8360 / 8260 / s8360 / 8360 / 268360 |
| DOMAIN_ID / primary entity | 0 (Campus Course Catalogue and Enrolment) / Course |
| Pipeline | HW9 ingress + semantic cache (threshold 0.95) in front of the HW8 Planner, Writer, Reviewer on Kafka 3.8.0 |
| Agents | qwen3:8b via Ollama, temperature 0, seed 8360 |
| Judge | DeepEval GEval on qwen3:8b via Ollama, temperature 0, seed 8360, think off, 1-5 rubric, 90 s timeout per call, 2 attempts |
| Trace file | kafka_state/traces/spans.jsonl (copied to reports/hw10/raw/spans.jsonl); trace_id = HW8 correlation_id |

## Part 2 - evaluation of the pipeline (scores 1-5)

| Case | Question | Plan | Writer draft | Final answer | Final - draft |
|---|---|---|---|---|---|
| c01 | How many seats are available in DATA-260? | 4 | 5 | 5 | 0 |
| c02 | Who teaches Web Programming? | 3 | 4 | 5 | 1 |
| c03 | How many seats do the Computer Science courses offer in total? | 4 | 4 | 5 | 1 |
| c04 | Which course has the most available seats? | 3 | 4 | 5 | 1 |
| c05 | How many courses does Dr. Marcus Lee teach? | 3 | 5 | 5 | 0 |
| c06 | Which department has the most available seats, and which course there has the most seats? | 3 | 4 | 4 | 0 |
| c07 | List the courses in the Data Science department. | 3 | 4 | 5 | 1 |
| c08 | What time does DATA-260 meet? | 4 | 2 | 1 | -1 |

## Part 4.2 - the three required traces

| Trace | trace_id | Result |
|---|---|---|
| Cache hit | `b86ddd2a-ea86-43b1-a33a-b427fcec3b86` | {'is_cached': True, 'similarity': 1.0, 'latency_ms': 207.1, 'answer': 'The course DATA-260 has 40 seats available.'} |
| Cache miss (success) | `7c6d4004-62b8-4ff2-9543-ba63dfc36cfd` | {'is_cached': False, 'status': 'approved', 'latency_ms': 11785.4, 'answer': 'The instructor who teaches DATA-230 is Dr. Samuel Okafor.'} |
| Failed | `dad26c70-f9ad-4657-a0e9-8413fc0b173d` | {'is_cached': False, 'status': 'timeout', 'latency_ms': 25810.9, 'answer': None} |

## Part 4.3 - stage latency over 50 confirmed cache misses

| Stage | p50 (ms) | p95 (ms) | % of cache-miss end-to-end |
|---|---|---|---|
| Cache lookup | 31.8 | 52.2 | 0.3 |
| Planner | 3569.6 | 4231.8 | 30.3 |
| Writer | 7865.3 | 10039.0 | 69.1 |
| Reviewer | 4.8 | 12.9 | 0.1 |
| Queue wait (total) | 43.7 | 58.4 | 0.4 |
| Evaluation | 29958.4 | 36011.3 | 262.4 |
| End-to-end (request span) | 11614.3 | 13866.6 | 100 |

Dominant contributor on the request path: **Writer** (69.1% of the end-to-end time). Cache-hit latency (separate metric, 30 hits): p50 13.1 ms, p95 20.1 ms. Candidate questions discarded because the cache answered: 1.

## Part 3 - judge validation (20 drafts)

| Measure | Value |
|---|---|
| Spearman rho (human vs judge, run 1) | 0.120 (p = 0.6138) |
| Mean absolute difference | 1.45 |
| Bias (judge - human) | -0.15 |
| Exact agreement / within one point | 25% / 60% |
| Repeatability: cases with any change over 3 runs | 0 of 20 |
| Mean / max absolute change between runs | 0.000 / 0 |

Verdict: I would NOT trust this judge to gate a deployment yet: rank agreement with the humans is 0.12 (threshold 0.80); the judge is off by 1.45 points on average (threshold 0.50); only 20 labeled cases are far too few to set a deployment gate (at least 100 are needed).

## Checks

`python tests_hw10.py` (offline tests) and `python verify_hw10.py` (live smoke test, writes `verification.json`).
