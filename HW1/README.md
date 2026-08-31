# DATA-260 Homework 1 — Karthik Pragada (SID4: 8360)

## Reproducible run instructions

All commands below assume you're inside this `HW1/` directory (`cd HW1` from the repo root first).

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
