# METRICS.md — DATA-260 Homework 2

All experiments run with `qwen3:8b` (Ollama, local), temperature 0.7, via
`python run_schema_experiment.py`. Full per-run records: `reports/hw02/raw/*.json`.
Console output with timestamps: `reports/hw02/RUN_LOG.txt`.

## Part 4.3 — 30 runs, fixed input, ceiling = 6

Input: `reports/hw02/cases/schema_input.json` (cloud-computing/Kubernetes course).

| Outcome over 30 runs | Count | Mean latency (ms) |
|---|---|---|
| Valid first attempt | 30 | 5625.7 |
| Valid after 1 retry | 0 | — |
| Valid after 2+ retries | 0 | — |
| Hit turn ceiling | 0 | — |

Every run's first Planner draft cleared both the Pydantic schema gate and the
Reviewer on the first pass — the self-correction loop never fired on this input.

## Part 4.4 — turn ceiling comparison (same fixed input, 20 runs each)

| Ceiling | n | Completion rate | Mean latency (ms) |
|---|---|---|---|
| 2 | 20 | 0% | 2387.6 |
| 10 | 20 | 100% | 5705.9 |

**Structural explanation:** the shortest possible successful path through the graph
is 4 supervisor visits (planner → validate → reviewer → end-check). At `ceiling=2`,
`router_logic()`'s ceiling check fires on the 3rd supervisor visit
(`turn_count=3 > 2`) — before the Reviewer node ever runs — so every run is
abandoned regardless of model quality; the low mean latency (2387.6 ms) reflects the
graph being cut short, not a faster success. At `ceiling=10`, every run completes
normally in 4 visits, matching the `ceiling=6` baseline from 4.3 (5705.9 ms vs.
5625.7 ms, within normal LLM-latency noise).

**Chosen ceiling for deployment: 6.** The minimum viable ceiling is 4 (the length of
the no-retry happy path); `ceiling=2` is provably too low and can never complete a
single run. Both `ceiling=6` and `ceiling=10` complete 100% of runs on this input at
statistically indistinguishable latency, so completion rate alone doesn't
differentiate them. The deciding factor is Part 4.5: the adversarial input shows that
even one self-correction retry needs a 7th supervisor visit, so any ceiling that
doesn't comfortably clear "happy path + one retry cycle" (4 + 3 = 7 visits) will
systematically punish legitimate self-correction. `ceiling=6` sits right at that
boundary (as 4.5 demonstrates, it's one visit short), while `ceiling=10` gives a full
retry cycle room to complete and be re-reviewed without materially increasing latency
on the runs that don't need it. We'd deploy with **`ceiling=10`** rather than the
`ceiling=6` used for these experiments, specifically because 4.5's data shows 6 is not
enough to let a single genuine correction finish.

## Part 4.5 — adversarial input, 5 runs, ceiling = 6

Input: `reports/hw02/cases/adversarial_input.json` — a course description
deliberately written to span ten unrelated CS subfields in one semester, chosen to be
hard to compress into 3 specific, accurate tags.

| n | Runs that hit the ceiling | Rate |
|---|---|---|
| 5 | 5 | 100% (5/5) |

This clears the "at least 4 of 5" preference from the assignment.

**Per-run detail:** all 5 runs needed exactly one self-correction retry (the first
draft is specific/narrow, the Reviewer flags it as not reflecting the course's
breadth, the Planner revises toward broader tags). One self-correction retry costs 3
extra supervisor visits, putting the second Reviewer verdict at `turn_count=7`.
Because `router_logic()` checks the turn ceiling *before* it ever inspects the
Reviewer's feedback, that 7th visit is caught by the `ceiling=6` check regardless of
whether the second review actually approved the revision — in one of these runs the
second review came back `"has_issues": false` and the run was *still* logged as
abandoned, because the router never reached the branch that would have read it. Mean
latency (14457.4 ms) is roughly 2.6× the fixed-input baseline from the extra
Planner/Reviewer round trip.

**Why it causes trouble:** the assignment's own choice of `ceiling=6` for this
experiment is exactly one supervisor visit short of "happy path + one retry" (7
visits). Any input that reliably needs even a single genuine self-correction will be
misclassified as "abandoned" under this ceiling, even when the correction actually
succeeded — the ceiling check firing before the feedback check means a legitimately
finished, Reviewer-approved run and a still-broken run are indistinguishable from the
`abandoned_at_ceiling` label alone.

**Proposed fix:** raise the deployment ceiling to at least 10 (see 4.4) so a full
happy-path-plus-one-retry cycle (7 visits) always has headroom to finish and be
re-reviewed before the ceiling fires. As a complementary, lower-cost fix that doesn't
require touching the ceiling value at all: reorder the two checks at the top of
`router_logic()` so a **fresh, not-yet-evaluated** Reviewer verdict is read before the
ceiling check is applied — i.e., only treat a run as `abandoned_at_ceiling` if the
ceiling is hit *and* there is no pending approved feedback to act on. That would have
correctly published the "has_issues: false" run in 4.5 as a normal completion instead
of an abandonment, without changing how many retries are allowed.
