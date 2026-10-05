# METRICS.md — DATA-260 Homework 5

SID4 8360 · PORT_BASE 8260 · PREFIX s8360 · SEED 8360 · VERIFY_SEED 268360 · DOMAIN_ID 0 (Campus Course Catalogue and Enrolment).
Hardware: MacBook Air, Apple M4, 16 GB RAM. Local model: `qwen3:8b` via Ollama (Part 5 agent), temperature 0. Database: MySQL 8.0 (Docker), `s8360_rel`.

## Part 3 — Fault injection (150 calls)

Retry policy under test (`resilience.INTERACTIVE`): 3 attempts, 1.0 s timeout per attempt, backoff 0.05 s then 0.10 s (factor 2, cap 0.5 s).
Faults are injected into the real MySQL-backed repository by a RNG re-seeded with `VERIFY_SEED = 268360` for every rate, so the same seed gives the same
success/failure sequence (verified by re-running all 150 calls: identical). Calls cycle through `search_courses`, `course_detail`, `course_stats`.
One uncounted warm-up query runs first so connection-pool start-up cost does not distort p99.

| Injected failure rate | Success rate | Mean latency (ms) | p99 latency (ms) |
|---|---|---|---|
| 0% | 100.0% (50/50) | 5.84 | 11.07 |
| 20% | 100.0% (50/50) | 14.76 | 63.00 |
| 50% | 90.0% (45/50) | 41.29 | 160.19 |

Extra detail (from `raw/fault_injection_calls.json`): at 20%, 10 faults were injected and 10 calls needed a retry (40 succeeded first try, 10 on the second).
At 50%, 33 faults were injected; 30 calls succeeded first try, 12 on the second, 3 on the third, and 5 failed all three attempts and returned a clean
`{ok:false}` error. Raw data: `raw/fault_injection_calls.csv` / `.json` (all 150 calls), `raw/fault_injection_summary.json`.

**Interactive suitability.** At 0% and 20% the policy hides the faults completely (100% success) and the worst call still finishes in ~63 ms, which an
interactive assistant tolerates. At 50% a user would see 1 call in 10 fail and the slowest calls take ~160 ms, still acceptable for a chat turn; the worst
case is bounded at `3 x 1.0 s + 0.15 s ≈ 3.15 s`, which is why the timeout is only 1 s. A 50% fault rate is an outage, so surfacing a clean error quickly is the
right behaviour there.

**Batch processing.** Latency does not matter, completeness does, so I would raise `max_attempts` to about 6, the per-attempt timeout to ~10 s, and use
longer backoff (0.5 s base, factor 2, cap ~8 s, with random jitter so parallel workers do not retry in lockstep). At a 50% fault rate, 6 attempts would lower the
chance of a call failing outright from 1/8 (12.5%) to 1/64 (about 1.6%) (the injected rate per attempt is 0.5, so P(all attempts fail) = 0.5^n). I would also log permanently-failed
items to a dead-letter list for a later re-run rather than dropping them.

## Part 4 — Offline tests

`python tests_hw5.py`: **12/12 PASS** (valid + invalid input for each of the three tools, envelope shape, `execute_tool` never raising, retry recovery and
exhaustion with a fake clock, the Part 5 safety-rule block, and `run_agent` stopping at `max_steps` with `MockModel`). Runs with no database, network, API key or LLM.

## Part 5 — Agent scenarios (local Ollama `qwen3:8b`, real MySQL tools)

| Scenario | max_steps | Step count | Stop reason | Tool calls |
|---|---|---|---|---|
| S1 simple search | 6 | 2 | final_answer | 1 |
| S2 search + lookup | 6 | 2 | final_answer | 1 |
| S3 aggregate | 6 | 2 | final_answer | 1 |
| S4 sensitive request | 6 | 1 | final_answer | 0 |
| S5 two-step ceiling | 2 | 2 | final_answer | 1 |
| S6 forced sensitive call | 6 | 1 | safety_block | 1 |
| S7 one-step ceiling | 1 | 1 | max_steps | 1 |

Notes: in S4 the model refused the password request itself, so the safety rule was never needed; S6 (the prompt tells the model to call the tool with the
sensitive query) is the run where `execute_tool` blocked the call. S5 finished inside its 2-step ceiling; S7 (ceiling of 1) is the run that hit `max_steps`.
Full step-by-step log: `raw/agent_runs.jsonl` (25 records, 7 runs).

## Part 1 / 2 summary

Part 1 API check script: **24/24** requests matched the expected status code (`raw/api_demo_calls.json`). Part 2: both MCP servers answered every probe over
real STDIO and in the MCP Inspector (`raw/mcp_inspector/`).
