# METRICS - DATA-260 Homework 8

Numbers come from the files in `reports/hw08/raw/` (one run each; unkeyed partitioning is random, so the exact ordering numbers differ from run to run).

## Configuration

| Value | Setting |
|---|---|
| SID4 / PORT_BASE / PREFIX / SEED / VERIFY_SEED | 8360 / 8260 / s8360 / 8360 / 268360 |
| DOMAIN_ID / primary entity | 0 (Campus Course Catalogue and Enrolment) / Course |
| Broker | Apache Kafka 3.8.0, KRaft, one broker, replication factor 1 |
| Client library | confluent-kafka 2.16.1 (acks=all, idempotent producer, manual offset commit) |
| Part 2 model | qwen3:8b via Ollama, temperature 0, seed 8360 (Parts 1 and 3 use no model) |


## Part 2 - one message journey (correlation_id 57c72d04-3ef8-4b88-b19d-8c7b08948f1b)

| Stage | Seconds |
|---|---|
| question sent -> Planner receives | 0.51 |
| Planner (qwen3:8b plan) | 7.33 |
| tasks topic -> Writer receives | 0.02 |
| Writer (facts + qwen3:8b draft) | 5.47 |
| drafts topic -> Reviewer receives | 0.01 |
| Reviewer (deterministic checks) | 0.0 |
| final topic -> client receives | 0.01 |
| end to end | 13.35 |

## Part 3 - failure behaviour (before / after)

| Failure scenario | Before fix | After fix |
|---|---|---|
| Duplicate delivery | replayed correlation_id -> 2 drafts published (side effect twice) | 1 draft; replay logged as DUPLICATE and skipped |
| Consumer killed mid-work | offset auto-committed before the work finished: lag after kill 0, redelivered after restart: False, drafts 0 (message lost) | offset committed after the draft: lag after kill 1, redelivered: True, drafts 1 |
| Poison message | writer exits with code 1 on it, again after restart (1); later message processed: False; lag 2 | 3 attempts, then dead-letter record at offset 7; later message processed: True; lag 0 |
| Two partitions / two consumers | no key: 4 order inversions, 2/5 entities in order, 1/5 in one partition | key = course code: 0 inversions, 5/5 entities in order, 5/5 in one partition |

## Part 3 - ordering detail (VERIFY_SEED 268360, 20 messages)

| Entity | Messages | No key: partitions | No key: processed seq order | Key: partitions | Key: processed seq order |
|---|---|---|---|---|---|
| CS-146 | 7 | [0, 1] | [1, 4, 5, 2, 3, 6, 7] | [0] | [1, 2, 3, 4, 5, 6, 7] |
| CS-157A | 1 | [0] | [1] | [1] | [1] |
| DATA-245 | 3 | [0, 1] | [1, 2, 3] | [0] | [1, 2, 3] |
| DATA-270 | 4 | [0, 1] | [4, 1, 2, 3] | [0] | [1, 2, 3, 4] |
| STAT-200 | 5 | [0, 1] | [2, 1, 5, 3, 4] | [0] | [1, 2, 3, 4, 5] |

## Checks

`python tests_hw8.py` (25 offline tests) and `python verify_hw08.py` (live smoke test, writes `verification.json`).
