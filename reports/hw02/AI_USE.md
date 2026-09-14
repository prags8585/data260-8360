# AI_USE.md — DATA-260 Homework 2


## 1. What did you use an AI assistant for, and what did you do yourself?

I used Claude (via Claude Code) for:

- Reviewing my personally drafted `report.pdf` against the actual repository contents (code,
  screenshots, terminal output) before submission.
- Drafting the rubric-required companion files for `reports/hw02/`: `METRICS.md`,
  `verification.json` (plus the `verify_hw02.py` smoke-test script that produces it),
  and `RUN_LOG.txt` (from a fresh, live 75-run re-execution of `run_schema_experiment.py`).
- Git operations: committing, pushing, and tagging the `hw2` submission commit.

## 2. One AI-produced output that was wrong/unsuitable, or one thing you independently verified
The model was running at `temperature=0.7`, the new run
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

Re ran the updated code and the second review came
back clean (`has_issues: false`), but the run was still abandoned because the ceiling
check in `router_logic()` runs before the feedback check, so the approval never gets a
chance to route to `END`. This version is verifiably accurate because the transcript is
copied verbatim from a real, reproducible run (and can be reproduced again by re-running
the same command) rather than being reconstructed from memory or substituted with a
different sample.
