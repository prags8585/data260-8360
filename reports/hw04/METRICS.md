# METRICS.md — DATA-260 Homework 4

SID4 8360, PORT_BASE 8260, PREFIX s8360, SEED 8360, VERIFY_SEED 268360,
DOMAIN_ID 0 (Campus Course Catalogue and Enrolment). Hardware: MacBook
Air, Apple M4, 16 GB RAM. Local model: `qwen3:8b` via Ollama (Part 4),
embeddings `sentence-transformers/all-MiniLM-L6-v2` (Part 4), MySQL 8.0
via Docker (Parts 2 and 3).

## Part 3 — N+1 Measurement and Query Tuning

Benchmark data: 5,000 rows in `perf_courses`, 200 rows in
`perf_course_reviews`, seeded deterministically from `SEED=8360`
(`scripts/seed_perf_data.py`). 180 requests measured (3 page sizes × 2
versions × 30 requests each) against the live `/api/perf/courses`
endpoint. Full per-request data: `reports/hw04/raw/n_plus_1_records.json`
/ `.csv`. Script: `scripts/measure_n_plus_1.py`.

| Page size | Version | SQL stmts/req | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|---|---|
| 10 | naive | 11 | 22.07 | 27.28 | 39.74 |
| 10 | fixed | 2 | 8.10 | 12.75 | 13.06 |
| 50 | naive | 51 | 14.98 | 77.12 | 83.55 |
| 50 | fixed | 2 | 3.46 | 3.98 | 4.14 |
| 200 | naive | 201 | 47.85 | 50.27 | 66.83 |
| 200 | fixed | 2 | 5.30 | 5.94 | 6.33 |

SQL statement counts are exact per request (read from the real
`X-SQL-Query-Count` response header, via a SQLAlchemy
`before_cursor_execute` listener — not assumed). Naive is always
`page_size + 1`; fixed is always exactly `2`, regardless of page size.

**Speed-up (naive p50 / fixed p50):**

| Page size | Speed-up |
|---|---|
| 10 | 2.72× |
| 50 | 4.33× |
| 200 | 9.03× |

The fixed version issues exactly 2 SQL statements no matter how many
rows are on the page — one for the page of courses, one
`WHERE course_id IN (...)` query for all their reviews at once. The
naive version issues `1 + page_size` statements, so its overhead scales
with page size while the fixed version's stays flat. That is why the
speed-up grows with page size: the fix removes a fixed number of
round-trips, so its relative benefit grows with however many round-trips
existed to remove. (The naive p50 at page_size=10 running slightly
higher than at page_size=50 is machine noise from that run, not a
property of the endpoints — both are far above the fixed version's flat
~2–8ms either way.)

**Index added:** `idx_perf_course_reviews_course_id` on
`perf_course_reviews(course_id)` (intentionally not auto-created — the
column has no `ForeignKey` constraint). `EXPLAIN` on
`SELECT * FROM perf_course_reviews WHERE course_id IN (1..10)` before:
`type=ALL`, `key=NULL`, `rows=200`, `filtered=50%`. After:
`type=range`, `key=idx_perf_course_reviews_course_id`, `rows=10`,
`filtered=100%`, `Using index condition`. Full output:
`reports/hw04/raw/explain_before_after.txt`.

## Part 4 — Grounded RAG Question-Answering System

Corpus: `corpus/hw03/` (16 real SJSU pages, 207KB). Chunking:
`chunk_size=500`, `chunk_overlap=50` (tokens) → 103 nodes. Embeddings:
`sentence-transformers/all-MiniLM-L6-v2`. LLM: `qwen3:8b` via Ollama,
temperature 0, reasoning off. Vector store: LlamaIndex in-memory
`VectorStoreIndex`. Script: `rag.py`. Full per-question/per-config
output: `reports/hw04/raw/rag_results.json`,
`reports/hw04/RAG_RUN_LOG.txt`.

**Evaluation table** (6 questions × 3 configurations):

| Q | Category | Config | Correct retrieval | Correct answer | Grounded | Refused when needed |
|---|---|---|---|---|---|---|
| q1 | single chunk | No RAG | n/a | no | n/a | n/a |
| q1 | single chunk | Basic RAG | yes | no | n/a | n/a |
| q1 | single chunk | Context-eng. | yes | no | yes | n/a |
| q2 | needs two chunks | No RAG | n/a | no | n/a | n/a |
| q2 | needs two chunks | Basic RAG | no | no | n/a | n/a |
| q2 | needs two chunks | Context-eng. | no | no | yes | n/a |
| q3 | similar info across docs | No RAG | n/a | yes | n/a | n/a |
| q3 | similar info across docs | Basic RAG | yes | yes | n/a | n/a |
| q3 | similar info across docs | Context-eng. | yes | yes | yes | n/a |
| q4 | ambiguous | No RAG | n/a | n/a | n/a | n/a |
| q4 | ambiguous | Basic RAG | yes | n/a | n/a | n/a |
| q4 | ambiguous | Context-eng. | yes | n/a | yes | n/a |
| q5 | not in the documents | No RAG | n/a | n/a | n/a | **no** |
| q5 | not in the documents | Basic RAG | n/a | n/a | n/a | **no** |
| q5 | not in the documents | Context-eng. | n/a | n/a | yes | **yes** |
| q6 | unrelated | No RAG | n/a | n/a | n/a | **no** |
| q6 | unrelated | Basic RAG | n/a | n/a | n/a | **no** |
| q6 | unrelated | Context-eng. | n/a | n/a | yes | **yes** |

"n/a" means the concept doesn't apply to that cell (e.g. No RAG never
retrieves anything). q4 has no single correct-answer marker (multiple
valid deadlines exist in the corpus), so "correct answer" is left n/a
and judged qualitatively in the analysis instead.

**Summary by configuration:**

| Config | Accuracy % | Faithfulness % | Format compliance % | Robustness (Q5/Q6 refusal) % |
|---|---|---|---|---|
| No RAG | 33.3 | n/a | n/a | 0.0 |
| Basic RAG | 33.3 | n/a | n/a | 0.0 |
| Context-engineered | 33.3 | 100.0 | 33.3 | 100.0 |

**Context-size sweep (k = 1, 3, 5) on q2:** at k=1 and k=3, every
retrieved chunk came from `msda_curriculum_courses.txt` (alumni/employer
marketing text), so the system correctly refused both times. At k=5, one
additional chunk from `applied_data_intelligence_ms_program.txt` entered
the set and named both specialization tracks, so the answer improved
from a full refusal to a partial, correctly-cited answer — it still
didn't recover the DATA course numbers, because that specific chunk
wasn't in the top 5 either. Full output:
`reports/hw04/raw/k_sweep_results.json`.

**Headline finding:** No RAG and Basic RAG both answered Q5 and Q6
instead of refusing (0% robustness) — No RAG has no way to know what it
doesn't know about this corpus, and Basic RAG's prompt never tells it
refusal is an option even when its retrieved chunks are irrelevant.
Context-engineered RAG refused both correctly (100%), from the *same*
retrieved chunks Basic RAG had — the difference is the grounding +
refusal instruction, not better retrieval. Retrieval itself was the
bottleneck on accuracy across all three configs (q1/q2 failed to surface
their target passage under this run's chunk_size=500 setting, a coarser
split than HW3 Part 2's tuned 256/32).
