# AI_USE.md — DATA-260 Homework 2

> **Draft note:** this file was drafted by Claude based on what it directly observed in
> our working session (the report-review/correction pass and the rubric-completion pass).
> It does not have visibility into how much AI assistance went into the earlier coding
> sessions that produced `agent_graph.py`, `run_schema_experiment.py`, and the FastAPI
> app before this conversation started. Please review and edit the first answer below to
> accurately reflect your own process for Parts 1–4, then delete this note.

## 1. What did you use an AI assistant for, and what did you do yourself?

I used Claude (via Claude Code) for:

- Reviewing my assembled `report.pdf` against the actual repository contents (code,
  screenshots, terminal output) before submission, to catch places where the write-up
  didn't match what the code actually does.
- Re-running the Part 3/4 `agent_graph.py` demo commands live against my local Ollama
  instance to verify terminal transcripts in the report were genuine and reproducible,
  rather than reconstructed from memory.
- Drafting the rubric-required companion files for `reports/hw02/`: `METRICS.md`,
  `verification.json` (plus the `verify_hw02.py` smoke-test script that produces it),
  and `RUN_LOG.txt` (from a fresh, live 75-run re-execution of `run_schema_experiment.py`).
- Identifying gaps against the actual HW2 assignment PDF (missing `RUN_LOG.txt`,
  `METRICS.md`, `AI_USE.md`, `verification.json`; missing GitHub collaborator access;
  missing "choose a ceiling for deployment" / "propose one fix" analysis required by
  Part 4).
- Git operations: committing, pushing, and tagging the `hw2` submission commit.

*(Fill in: describe what you personally wrote/designed for Parts 1–4 — the FastAPI
CRUD routes, the HTML/CSS responsive layout, the LangGraph `AgentState`/nodes/router,
the Pydantic schema gate, the experiment harness in `run_schema_experiment.py` — and
how much of that used AI assistance versus was written by you directly.)*

## 2. One AI-produced output that was wrong/unsuitable, or one thing you independently verified

While reviewing a draft of the report, Claude had regenerated the Part 4 "adversarial
input" demo transcript by re-running `agent_graph.py --input
reports/hw02/cases/adversarial_input.json` itself, rather than using the transcript
from my own original run. Because the model runs at `temperature=0.7`, the new run
produced different (but structurally similar) output: different specific tag text, and
— more importantly — the write-up ended up describing the Reviewer's second verdict as
still flagging an issue, when in my actual original run the Reviewer's second verdict
was `"has_issues": false` (the run was still logged as abandoned only because
`router_logic()` checks the turn ceiling before it reads the Reviewer's feedback).

## 3. How you detected the problem or verified the result

I compared the regenerated section against the terminal screenshot from my own earlier
run of the same command and noticed the tag text and the Reviewer's feedback text
didn't match what I had actually seen on my machine.

## 4. What you changed and why it works now

I asked Claude to use my actual original transcript instead of a fresh rerun, and to
correct the explanation to describe what genuinely happened: the second review came
back clean (`has_issues: false`), but the run was still abandoned because the ceiling
check in `router_logic()` runs before the feedback check, so the approval never gets a
chance to route to `END`. This version is verifiably accurate because the transcript is
copied verbatim from a real, reproducible run (and can be reproduced again by re-running
the same command) rather than being reconstructed from memory or substituted with a
different sample.
