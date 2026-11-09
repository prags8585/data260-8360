# DATA-260 Homework 1 — Karthik Pragada (SID4: 8360)

## Reproducible run instructions

```bash
# One-time setup
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
pip install langchain-ollama langchain-core
ollama pull qwen3:8b

# Part 1 -- static site
python -m http.server 8260          # or: docker build -t data260-8360-hw1 . && docker run -d -p 8260:8260 --name hw1-app data260-8360-hw1
open http://localhost:8260

# Part 2 -- agent demo
python agents_demo.py

# Part 3 -- non-determinism sweep (40 runs, ~1 hour)
python run_nondeterminism.py

# Part 4 -- model client / token accounting CLI
python hw1_client.py
```

## Part 4 — Model Client and Token Accounting

`src/model_client.py` defines `ModelClient`, a reusable adapter with a stable `complete(messages, tools=None)` interface over a local Ollama chat model. `hw1_client.py` is a small CLI chat demo built on top of it, loading `AGENT.md` as the system prompt (instructing strict bullet-only code review) and printing per-turn and cumulative token usage, plus a `/stats` command.

### Q: Why is prior conversation context resent with every turn?

Because the model itself is stateless between API calls -- it has no memory of earlier turns unless that content is physically included in the current request. Each call to `ChatOllama.invoke()` (and the underlying Ollama HTTP API call it makes) is an independent forward pass over exactly the tokens it's given. For the model to "remember" what was said three turns ago, the client has to literally re-send the entire prior conversation -- system prompt plus every past user and assistant message -- as part of the input to every new call. This is why `hw1_client.py` keeps its own `history` list and passes the whole thing to `client.complete()` on every turn, not just the newest message.

### Q: How is a system prompt different from a user message?

A system prompt is a separate message role that sets persistent, session-wide behavioral rules for the model -- it configures *how* the model should respond (format, tone, constraints), rather than being something anyone "said" in the conversation. It's typically treated as higher-priority, foundational instruction that should hold across every subsequent turn. A user message, by contrast, is an actual turn in the conversation -- a specific question or request the model is expected to respond to directly. In this project, `AGENT.md`'s "respond only in bullet points" instruction is loaded once as the system prompt and governs every response in the session, while each `"Review this: ..."` message is a distinct user turn.

### Q: Why do input tokens grow over a conversation?

Directly because of the first answer: every turn resends the full history so far. Turn 1's input is just the system prompt plus the first user message; turn 2's input is the system prompt *plus* turn 1's user message *plus* turn 1's assistant response *plus* the new turn-2 user message; and so on. Since each new call's input is a strict superset of the previous call's input (plus whatever was just added), input token counts are monotonically non-decreasing across a conversation. This was directly observed in our own run: input tokens climbed 146 -> 198 -> 254 -> 308 -> 367 across 5 turns, tracking the growing history length exactly.

### Q: What eventually limits that growth?

The model's context window -- the maximum number of tokens it can accept in a single call. Our `qwen3:8b` instance is configured with a 4096-token context (visible via `ollama ps`). Once system prompt + accumulated history + new message would exceed that limit, something has to give: older turns must be dropped, summarized, or the call fails outright. In practice, real systems manage this proactively -- truncating or summarizing older context, capping conversation length, or using retrieval instead of full history -- both because of this hard ceiling and because cost/latency scale with input size long before the ceiling is ever reached.

# DATA-260 Homework 2 — Karthik Pragada (SID4: 8360)

## Reproducible run instructions

```bash
# One-time setup (reuses the same venv/model as HW1)
source .venv/bin/activate
pip install fastapi "uvicorn[standard]" jinja2 python-multipart langgraph pydantic
ollama pull qwen3:8b

# Part 1 & 2 -- FastAPI Course Catalogue app (PORT_BASE = 8260)
uvicorn main:app --host 0.0.0.0 --port 8260
open http://localhost:8260

# Part 3 -- stateful Planner/Reviewer agent graph
python agent_graph.py --temperature 0.7                        # baseline, ends normally
python agent_graph.py --temperature 0.7 --force-issue --ceiling 4   # forces the self-correction loop

# Part 4 -- schema gate demo runs
python agent_graph.py --input reports/hw02/cases/schema_input.json --temperature 0.7
python agent_graph.py --input reports/hw02/cases/adversarial_input.json --temperature 0.7 --ceiling 6

# Part 4 -- full batch experiments (30 + 20 + 20 + 5 = 75 runs, ~7 minutes)
# writes reports/hw02/raw/*.json and reports/hw02/raw/part4_summary.json
python run_schema_experiment.py

# Smoke test (starts the FastAPI backend and the agent graph, checks both
# actually respond/terminate correctly) -- writes reports/hw02/verification.json
python verify_hw02.py
```

# DATA-260 Homework 3 — Karthik Pragada (SID4: 8360)

## Reproducible run instructions

```bash
# One-time setup
source .venv/bin/activate
pip install itsdangerous llama-index llama-index-embeddings-huggingface \
    sentence-transformers faiss-cpu numpy pandas beautifulsoup4 pyyaml

# Part 1 -- FastAPI Bootstrap login/session app (extends the HW1/2 app)
# Self-signed local HTTPS cert (one-time), needed so the session cookie's
# Secure flag can be genuinely exercised rather than faked:
openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/localhost-key.pem \
    -out certs/localhost-cert.pem -days 365 -subj "/CN=localhost"
uvicorn main:app --host 0.0.0.0 --port 8260 \
    --ssl-keyfile certs/localhost-key.pem --ssl-certfile certs/localhost-cert.pem
open https://localhost:8260
# demo user: karthik / data260

# Part 2 -- re-fetch the domain corpus (already committed under corpus/hw03/,
# only needed to regenerate it from scratch)
python scripts/fetch_corpus.py /tmp/urls.txt

# Part 2 -- run the three-chunker retrieval comparison (~2-3 minutes)
# writes reports/hw03/raw/*.json|csv and reports/hw03/METRICS.md's source data
python rag_chunking_comparison.py --k 5

# Smoke test -- writes reports/hw03/verification.json
python verify_hw03.py
```


# DATA-260 Homework 7 — Karthik Pragada (SID4: 8360)

## Reproducible run instructions

```bash
# One-time setup (reuses the HW1-HW6 venv, MySQL and Ollama qwen3:8b)
pip install -r requirements.txt
PYTHONPATH=. python scripts/migrate_hw7.py          # users.username + users.role, demo reader/writer/moderator accounts
pre-commit install                                   # Ruff runs on every commit (config: pyproject.toml, .pre-commit-config.yaml)

# Part 1 -- JWT auth + roles (backend on PORT_BASE 8260)
SESSION_HTTPS_ONLY=false uvicorn main:app --port 8260
PYTHONPATH=. python scripts/hw7_auth_evidence.py     # real curl requests: 200 / 201 / 401 / 403 / 204

# Part 2 -- hand-written agent loop
PYTHONPATH=. python scripts/hw7_agent_demo.py        # tasks A, B, C and the nonexistent-id case
PYTHONPATH=. python scripts/hw7_reliability.py       # 30 attempts, well-formed call rate before/after repair

# Part 3 -- Reflexion
PYTHONPATH=. python scripts/hw7_reflexion_compare.py 10

# Part 4 -- LangGraph ReAct/MRKL agent (open http://localhost:8260/static/bikeshare.html)
PYTHONPATH=. python scripts/hw7_build_scenarios.py /path/to/202510-baywheels-tripdata.csv   # the two 520-row scenarios
PYTHONPATH=. python scripts/hw7_bikeshare_ui_demo.py # drives the UI for both scenarios

# Part 5 -- prompt injection
PYTHONPATH=. python scripts/hw7_attack_eval.py 2

# Part 6 -- file tools + safety gate
PYTHONPATH=. python scripts/hw7_file_tools_demo.py

# Offline tests and the smoke test (writes reports/hw07/verification.json)
python tests_hw7.py
PYTHONPATH=. python verify_hw07.py
```

HW4's cookie-session API was replaced by JWT bearer authentication in HW7 (`jwt_auth.py`); the session version is kept only at the `hw4` tag.

## Homework 8 — Kafka request/response, three-agent pipeline, failure behaviour

PREFIX `s8360`, PORT_BASE 8260, VERIFY_SEED 268360, primary entity Course. Code lives in `kafka_svc/` (config, course logic, Kafka helpers, RPC client, worker, FastAPI wrapper) plus `homework_demo.py`, `planner.py`, `writer.py`, `reviewer.py`, `send_question.py`.

```bash
docker compose -f docker-compose.kafka.yml up -d --build        # Kafka (KRaft), topic creation, worker, FastAPI on 8260
PYTHONPATH=. python homework_demo.py                             # Part 1: CREATE_COURSE -> GET_COURSE, merged log timeline
PYTHONPATH=. python homework_demo.py --via api                   # the same through the FastAPI wrapper
python planner.py; python writer.py; python reviewer.py          # Part 2: one terminal each (ollama serve + qwen3:8b running)
PYTHONPATH=. python send_question.py                             # Part 2: prints the final JSON from s8360_final
PYTHONPATH=. python scripts/hw8_failure_tests.py all             # Part 3: duplicate, consumer death, poison message, ordering
python tests_hw8.py && PYTHONPATH=. python verify_hw08.py        # offline tests, then the live smoke test (writes verification.json)
```

Writer switches used for the "before fix" runs: `--no-idempotency`, `--auto-commit`, `--no-dlq` (or `--naive` for all three). Port 8260 is also used by the HW7 `uvicorn main:app`; stop that first.

## HW9 - Redis counter, semantic response cache, self-improving agents

PREFIX `s8360`, PORT_BASE 8260, primary entity Course. Redis Stack runs in Docker on port 6382 (the Homebrew Redis on 6379 has no search module); all keys start with `s8360:`.
Code: `cache_svc/` (counter on `CourseDB`, vector cache, ingress API), `selfimprove/` (Answering Agent, Evaluator Agent, lessons), data in `cache_cases.yaml` and `part4/`.

```bash
docker compose -f docker-compose.cache.yml up -d                  # Redis Stack (vector index) on 6382
docker compose -f docker-compose.kafka.yml up -d kafka kafka-init # HW8 broker; planner.py / writer.py / reviewer.py as in HW8, with CATALOGUE_SOURCE=mysql for the writer
PYTHONPATH=. python scripts/hw9_migrate.py                        # adds courses.views
PYTHONPATH=. python scripts/hw9_part1_counter.py                  # Part 1: 25 accesses, sync to MySQL every 10th
PYTHONPATH=. uvicorn cache_svc.api:app --port 8260                # Part 2: POST /ask (semantic cache in front of the HW8 agents)
PYTHONPATH=. python scripts/hw9_part2_cache_demo.py               # Part 2: 12 queries, hit rate and latency
PYTHONPATH=. python scripts/hw9_threshold_sweep.py                # Part 3: 40 labeled cases (cache_cases.yaml) at 0.75 ... 0.95
PYTHONPATH=. python scripts/hw9_stale_demo.py                     # Part 3.5: stale hit and invalidation by data version
PYTHONPATH=. python scripts/hw9_export_reference.py               # Part 4: reference dataset from s8360_rel
PYTHONPATH=. python scripts/hw9_part4_run.py mine|validate|demo|final
python tests_hw9.py && PYTHONPATH=. python verify_hw09.py         # offline tests, then the live smoke test (writes verification.json)
```
