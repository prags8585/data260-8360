# METRICS.md — DATA-260 Homework 6

SID4 8360 · PORT_BASE 8260 · PREFIX s8360 · SEED 8360 · VERIFY_SEED 268360 · DOMAIN_ID 0 (Campus Course Catalogue and Enrolment).
Hardware: MacBook Air, Apple M4, 16 GB RAM. Local model: `qwen3:8b` via Ollama (temperature 0, reply capped at 160 tokens). MongoDB 7.0 (Docker), database `s8360_doc`.
Embeddings: `sentence-transformers/all-MiniLM-L6-v2` (384 dims). Component token counts are `tiktoken` `cl100k_base` proxies; prompt/completion totals are Ollama's own counters.

## Part 3 — Memory cost experiment

Same 30-message conversation (`memory_conversation.yaml`) replayed in a fresh user/session per setting, then the 5 probes in `memory_probes.yaml`
(written before the experiment; 1–5 rubric, deterministic element-match scoring). `SUMMARIZE_EVERY_USER_MSGS = 5`, `EPISODE_TOP_K = 3`, `MAX_FACTS_PER_MESSAGE = 3`.

| Setting | Mean prompt tokens / turn | Mean window tokens / turn | Mean latency (ms) / turn | Mean probe quality (1–5) |
|---|---|---|---|---|
| SHORT_TERM_N = 4 | 389.3 | 112.1 | 7,078.0 | 5.0 |
| SHORT_TERM_N = 12 | 644.2 | 327.8 | 9,314.0 | 5.0 |
| SHORT_TERM_N = 30 | 1,044.7 | 663.7 | 12,176.8 | 5.0 |
| Compression policy (N = 12) | 529.7 | 213.5 | 8,637.5 | 5.0 |

Eviction/compression policy: assistant turns older than the last 4 messages are cut to their first sentence (at most 20 words); user turns and the last 4 messages stay verbatim.
Against plain N = 12: **-114.5 prompt tokens/turn (-17.8%)**, -676.5 ms latency/turn (-7.3%), **probe quality unchanged (5.0 → 5.0, change 0.0)**.

Each `/api/chat` call also triggers memory maintenance (fact extraction every turn, summaries every 5th user message). That overhead was ~260 prompt and ~43
completion tokens per turn in every setting and is included in the cost estimate below. Raw per-turn data: `raw/short_term_sweep_turns.csv` / `.json`, probe replies and scores:
`raw/memory_probes_scoring.json`, summary: `raw/memory_settings_summary.json`.

### Cost of 10,000 conversations x 30 turns ($1.00 / M input, $5.00 / M output)

| Setting | Input tok/turn (chat + maintenance) | Output tok/turn | Input $ | Output $ | Total $ | Role |
|---|---|---|---|---|---|---|
| N = 4 | 649.0 | 93.6 | 194.70 | 140.40 | **335.10** | best |
| N = 12 | 906.3 | 95.1 | 271.89 | 142.65 | 414.54 | |
| N = 30 | 1,307.3 | 95.5 | 392.19 | 143.25 | **535.44** | worst |
| Compression, N = 12 | 788.1 | 91.6 | 236.43 | 137.40 | 373.83 | |

Best = cheapest setting within 0.5 probe-quality points of the top score (all four tie at 5.0, so N = 4 wins on cost); worst = most expensive. Moving from
N = 30 to N = 4 saves **$200.34 (37.4%)** per 10,000 conversations. Caveat: the probes only check five facts that were all captured as episodic facts or summaries,
so they cannot show a quality loss from a tiny window on tasks that need verbatim recent context; the choice is therefore "N = 4 for this fact-recall workload,
N = 12 with compression if the assistant must follow longer multi-step threads".

## Part 4 — File-based memory

| Item | Result |
|---|---|
| `AGENT.md` | 11 numbered instructions in 5 categories (project description, tech stack, coding conventions, testing approach, prohibited actions) |
| Function verified against it | `file_memory.memory_health_report` — `scripts/check_agent_md.py` 10/10 PASS |
| 55-line `MEMORY.md` | 55 lines / 50 entries → **39 lines** / 35 entries |
| Duplicates merged | 14 duplicate lines (e.g. `backend_port` x4, `name` x4) |
| Contradictions | 5 resolved explicitly (theme, graduation, advisor correct; work_hours and database_port incorrect, both flagged `NEEDS REVIEW`) |
| Offline tests | `tests_hw6.py` 13/13 PASS |

## Part 1 / 2 summary

Part 1 API check script: **17/17** requests matched the expected status (`raw/part1_api_calls.json`). Part 2: one 12-message session through `static/chat.html`
(`raw/part2_chat_ui.png`), memory and aggregate JSON in `raw/part2_memory.json` and `raw/part2_aggregate.json`.
