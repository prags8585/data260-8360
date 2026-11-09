# METRICS - DATA-260 Homework 9

Numbers come from the files in `reports/hw09/raw/` (one run each; model latencies vary from run to run, the hit/miss counts of the sweep do not).

## Configuration

| Value | Setting |
|---|---|
| SID4 / PORT_BASE / PREFIX / SEED / VERIFY_SEED | 8360 / 8260 / s8360 / 8360 / 268360 |
| DOMAIN_ID / primary entity | 0 (Campus Course Catalogue and Enrolment) / Course |
| Cache store | Redis Stack 7.4.7 (RediSearch 2.10.20) in Docker, host port 6382; FLAT vector index, FLOAT32, 384 dimensions, COSINE |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 (normalised, CPU) |
| Agent model | qwen3:8b via Ollama, temperature 0, seed 8360 |
| Labeled cases | `cache_cases.yaml`, 40 cases (20 should hit, 20 should miss), commit 5dc4149, sha256 a3057d2fc09db565... |

## Part 2 - 12-query demonstration (threshold 0.85)

| Measure | Value |
|---|---|
| Hit rate | 6/12 = 50.0% |
| Average latency, served from the cache | 27.5 ms |
| Average latency, agent pipeline (miss) | 4066.2 ms |

## Part 3 - threshold sweep (40 labeled cases)

| Threshold | Hit rate | False-hit rate | Mean latency | Misses | False hits | Total cost |
|---|---|---|---|---|---|---|
| 0.75 | 29/40 = 72.5% | 9/20 = 45.0% | 1202 ms | 11 | 9 | $9.1129 |
| 0.80 | 28/40 = 70.0% | 8/20 = 40.0% | 1352 ms | 12 | 8 | $8.1228 |
| 0.85 | 25/40 = 62.5% | 6/20 = 30.0% | 1942 ms | 15 | 6 | $6.1525 |
| 0.90 | 23/40 = 57.5% | 4/20 = 20.0% | 2122 ms | 17 | 4 | $4.1723 |
| 0.95 | 17/40 = 42.5% | 2/20 = 10.0% | 3154 ms | 23 | 2 | $2.2317 |

Cost model (fixed before the sweep): {'miss': 0.01, 'hit': 0.0001, 'false_hit': 1.0}. Chosen threshold: **0.95**. Cheapest threshold by false-hit cost ratio N (a false hit costs N misses): N=1: 0.80, N=3: 0.95, N=10: 0.95, N=30: 0.95, N=100: 0.95, N=300: 0.95.

| Category | Min similarity | Mean | Max |
|---|---|---|---|
| exact_duplicate | 1.0000 | 1.0000 | 1.0000 |
| paraphrase | 0.8334 | 0.9325 | 0.9867 |
| superficially_similar | 0.6332 | 0.8647 | 0.9676 |
| unrelated | 0.1017 | 0.1663 | 0.2456 |

## Part 3 - stale answer

| Step | Result |
|---|---|
| `DATA-260` seats before / after the UPDATE | 40 / 12 |
| Plain semantic cache after the UPDATE | serves "The course DATA-260 has 40 seats available." (stale) |
| With the data-version check | "The course DATA-260 has 12 seats available." (miss, stale entry invalidated, 7790 ms) |
| Version check cost on a hit | 4.3 ms |

## Part 4 - self-improving system

Training: 9/14 correct without lessons; repeated failure patterns: unsupported_answer:opinion x3, wrong_value:all_total_seats x2.
Validation gate: 1 of 2 candidate lessons kept.

| Variant | Correct | Incorrect | Average attempts | Average latency |
|---|---|---|---|---|
| Baseline | 10/18 | 8 | 1.0 | 1.29 s |
| Evaluator Repair | 18/18 | 0 | 1.44 | 2.18 s |
| Lesson Memory | 17/18 | 1 | 1.28 | 2.93 s |
| Validated Improvement | 18/18 | 0 | 1.22 | 2.68 s |

Lesson reuse demo: lesson `lesson_001` use_count after the later question = 1.

## Checks

`python tests_hw9.py` (38 offline tests) and `python verify_hw09.py` (live smoke test, writes `verification.json`).
