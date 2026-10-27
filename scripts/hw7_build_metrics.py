#!/usr/bin/env python3

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports/hw07/raw"


def load(name: str) -> dict:
    return json.loads((RAW / name).read_text())


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def money(x) -> str:
    return f"${x:,.2f}"


def part2() -> list[str]:
    d = load("reliability_summary.json")
    s, ops = d["summary"], d["opportunities"]
    per_case = defaultdict(lambda: [0, 0, 0])
    for o in ops:
        per_case[o["case"]][0] += 1
        per_case[o["case"]][1] += o["first_ok"]
        per_case[o["case"]][2] += o["first_ok"] or o["repaired"]
    rows = ["## Part 2 — Tool-use reliability (30 attempts, 3 fixed cases)", "",
            f"Same model settings for every attempt: qwen3:8b, temperature {s['temperature']}, num_predict 400; only the sampling seed changes ({s['seed_base']} + attempt). "
            "An *opportunity* is one model response where a tool call was required (70 in total); *before repair* counts only the first response, *after repair* "
            "counts the response to the single repair reprompt.", "",
            "| Measure | Result |", "|---|---|",
            f"| Opportunities (tool call required) | {s['opportunities']} |",
            f"| Well-formed calls before repair | {s['well_formed_before_repair']}/{s['opportunities']} = **{pct(s['rate_before_repair'])}** |",
            f"| Well-formed calls after repair | {s['well_formed_after_repair']}/{s['opportunities']} = **{pct(s['rate_after_repair'])}** |",
            f"| Attempts that needed a repair | {s['attempts_with_repair']}/{s['attempts']} |",
            f"| Attempts whose final answer passed the deterministic verifier | {s['attempts_verified']}/{s['attempts']} |",
            f"| Mean tool calls / latency per attempt | {s['mean_tool_calls']} / {s['mean_latency_ms'] / 1000:.1f} s |", "",
            "| Failure type | Count (first try) | Repaired by the single reprompt |", "|---|---|---|"]
    for t, n in s["failures_by_type"].items():
        rows.append(f"| {t.replace('_', ' ')} | {n} | {s['repaired_by_type'][t]} |")
    rows += ["", "| Case | Opportunities | Well-formed before repair | After repair |", "|---|---|---|---|"]
    for case, (n, a, b) in sorted(per_case.items()):
        rows.append(f"| {case} | {n} | {a} ({pct(a / n)}) | {b} ({pct(b / n)}) |")
    rows += ["", "Every first-try failure was a *lost multi-step chain* (the model answered after one call). No malformed arguments, unknown tools or "
             "text-instead-of-tool turns occurred in these 30 attempts. Raw data: `raw/reliability_attempts.csv`, `raw/reliability_opportunities.csv`, "
             "`raw/reliability_summary.json`, `raw/reliability_tool_log.jsonl`.", ""]
    return rows


def part3() -> list[str]:
    c = load("reflexion_comparison.json")["summary"]
    o, r = c["original"], c["reflexion"]
    p = load("verifier_probe.json")["summary"]
    rows = ["## Part 3 — Original loop versus Reflexion loop", "",
            f"Same three fixed tasks, {c['trials_per_case']} trials each (30 runs per loop), qwen3:8b at temperature {c['temperature']} (raised so that failures are observable). "
            "The first attempt of each Reflexion run uses the same seed as the paired original run.", "",
            "| Metric | Original loop | Reflexion loop |", "|---|---|---|",
            f"| Task success | {o['task_success']} ({pct(o['task_success_rate'])}) | {r['task_success']} ({pct(r['task_success_rate'])}) |",
            f"| Unsupported claims (per run; runs with any) | {o['unsupported_claims_per_run']} ({o['runs_with_unsupported_claims']}) | {r['unsupported_claims_per_run']} ({r['runs_with_unsupported_claims']}) |",
            f"| Retry rate (runs that retried; retries per run) | {pct(o['retry_rate_runs_with_retry'])}; {o['retries_per_run']} (no retry path) | {pct(r['retry_rate_runs_with_retry'])}; {r['retries_per_run']} |",
            f"| Tool calls (per run) | {o['tool_calls_per_run']} | {r['tool_calls_per_run']} |",
            f"| Tokens (per run, incl. reflection calls) | {o['tokens_per_run']:,.0f} | {r['tokens_per_run']:,.0f} |",
            f"| Latency (ms per run) | {o['latency_ms_per_run']:,.0f} | {r['latency_ms_per_run']:,.0f} |",
            f"| Verifier false rejections (of verification events) | {o['verifier_false_rejections']} of {o['verification_events']} | {r['verifier_false_rejections']} of {r['verification_events']} |", "",
            f"Stop reasons (Reflexion): {r['stop_reasons']}. Repair reprompts per run (the Part 2 repair path, present in both loops): {o['repair_reprompts_per_run']}.", "",
            "**Verifier false rejections.** In the 62 verification events of the main comparison the answer-only oracle (database ground truth) agreed with every verifier "
            "decision, so there were no false rejections. They do occur when the chain guard is off: in a supplementary probe (`scripts/hw7_verifier_probe.py`, "
            f"cases A and C, 10 trials each, no `required_tools` guard) the verifier rejected {p['verifier_rejections']} of {p['runs']} runs and **{p['false_rejections']} were false rejections** "
            "- all in case C, where the model compared the two courses from the seat counts and instructors in two `search_courses` results without calling `course_detail`. "
            "The answers were factually correct, but the verifier requires the detail lookups the task asks for. Raw data: `raw/reflexion_comparison.json`, "
            "`raw/reflexion_runs.csv`, `raw/reflections.jsonl`, `raw/verifier_probe.json`.", ""]
    return rows


def part4() -> list[str]:
    rows = ["## Part 4 — Bay Wheels membership vs pay-per-use (two acceptance scenarios)", "",
            "| Item | Scenario A (membership wins) | Scenario B (pay-per-use wins) |", "|---|---|---|"]
    res = {k: load(f"part4_scenario_{k}_result.json") for k in "AB"}
    cons = load("scenarios/scenario_construction.json")["scenarios"]
    a, b = res["A"], res["B"]
    sa, sb = cons["scenario_A_membership_wins.csv"]["summary"], cons["scenario_B_pay_per_use_wins.csv"]["summary"]
    rows += [
        f"| Trip rows | {sa['rows']} | {sb['rows']} |",
        f"| Date span / months | {sa['first_start'][:10]} to {sa['last_start'][:10]} / {a['costs']['months_spanned']} | {sb['first_start'][:10]} to {sb['last_start'][:10]} / {b['costs']['months_spanned']} |",
        f"| Bike mix | {sa['bike_mix']} | {sb['bike_mix']} |",
        f"| Pay-per-use total | {money(a['costs']['pay_per_use_total'])} | {money(b['costs']['pay_per_use_total'])} |",
        f"| Membership fee + residual = total | {money(a['costs']['membership_fee_total'])} + {money(a['costs']['membership_residual'])} = {money(a['costs']['membership_total'])} | {money(b['costs']['membership_fee_total'])} + {money(b['costs']['membership_residual'])} = {money(b['costs']['membership_total'])} |",
        f"| Break-even vs actual rides per month | {a['costs']['break_even_rides_per_month']} vs {a['costs']['actual_rides_per_month']} | {b['costs']['break_even_rides_per_month']} vs {b['costs']['actual_rides_per_month']} |",
        f"| **Agent decision** | **{a['decision']}** | **{b['decision']}** |",
        f"| Independent recomputation agrees | {all(a['check'].values())} | {all(b['check'].values())} |",
        f"| Steps / tool calls / total time | {a['metrics']['steps']} / {a['metrics']['tool_calls']} / {a['metrics']['total_seconds']} s | {b['metrics']['steps']} / {b['metrics']['tool_calls']} / {b['metrics']['total_seconds']} s |",
        f"| Stop reason | {a['metrics']['stop_reason']} | {b['metrics']['stop_reason']} |",
        f"| Pricing source URL | {a['snapshot']['url']} | {b['snapshot']['url']} |",
        f"| Access date/time (UTC) | {a['snapshot']['accessed_at']} | {b['snapshot']['accessed_at']} |",
        f"| SHA-256 of the saved page text | `{a['snapshot']['sha256']}` | `{b['snapshot']['sha256']}` |", "",
        "The trip CSVs are *constructed rider histories* built from 520 real rows of the public `202510-baywheels-tripdata.csv` (durations, bike types, stations and ids are real; "
        "start dates are assigned from a schedule because the public data has no rider id). See `raw/scenarios/scenario_construction.json`.", ""]
    return rows


def part5() -> list[str]:
    path = RAW / "attack_results.json"
    if not path.exists():
        return ["## Part 5 — Prompt-injection attacks", "", "(attack results not generated yet)", ""]
    d = load("attack_results.json")
    names = {"override": "Recommendation override", "sql_misuse": "Non-SELECT tool misuse", "exfiltration": "Data exfiltration"}
    labels = {"procedure": "scaffolded Part 4 agent (numbered procedure, SQL template)", "minimal": "stress configuration (same tools, short unscaffolded prompt)"}
    rows = ["## Part 5 — Prompt-injection attacks (scenario B, honest answer = Pay Per Ride/Minute)", "",
            f"Trials per cell: {d['trials']} at temperature {d['temperature']}. Cell = attacks that succeeded / trials (attempted / trials)."]
    for style in d["configs"]:
        rows += ["", f"**Configuration: {labels[style]}**", "",
                 "| Attack | Before defenses | After prompt defense | After prompt + tool defense |", "|---|---|---|---|"]
        for k, label in names.items():
            cells = [f"{d['summary'][style][k][c]['attack_succeeded']} succeeded ({d['summary'][style][k][c]['attempted']} attempted)" for c in ("before", "prompt", "prompt+tool")]
            rows.append(f"| {label} | " + " | ".join(cells) + " |")
    rows += ["", "Raw data: `raw/attack_results.json`, `raw/attack_results.csv`; hostile fixtures in `fixtures/hw07/`.", ""]
    return rows


def part6() -> list[str]:
    final = load("safety_gate_results_final.json")
    before = load("safety_gate_results_before_fix.json")
    rows = ["## Part 6 — File tools and safety gate", "",
            "| Run | Correct | False allows | False blocks |", "|---|---|---|---|",
            f"| First implementation (before the fix) | {before['correct']}/10 | {before['false_allows']} | {before['false_blocks'] or 'none'} |",
            f"| After the fix | {final['correct']}/10 | {final['false_allows'] or 'none'} | {final['false_blocks'] or 'none'} |", "",
            "| Command | Expected | Final decision | Reason |", "|---|---|---|---|"]
    for r in final["results"]:
        rows.append(f"| `{r['command']}` | {r['expected']} | {'allow' if r['allowed'] else 'block'} | {r['reason']} |")
    rows += ["", "The false allow was `sort -o /etc/hosts notes.txt`: `sort` is on SAFE_PREFIXES and the write to a root path happens through its own `-o` output option, "
             "not through a shell redirection, so the first `is_destructive` did not see it. Fixed by checking output options (`-o`, `--output`, `date -s`, `uniq IN OUT`) "
             "for absolute paths. Raw data: `raw/safety_gate_results_before_fix.json`, `raw/safety_gate_results_final.json`.", ""]
    return rows


def main() -> None:
    head = ["# METRICS.md — DATA-260 Homework 7", "",
            "SID4 8360 · PORT_BASE 8260 · PREFIX s8360 · SEED 8360 · VERIFY_SEED 268360 · DOMAIN_ID 0 (Campus Course Catalogue and Enrolment).",
            "Hardware: MacBook Air, Apple M4, 16 GB RAM. Local model: `qwen3:8b` via Ollama. Database: MySQL 8.0 (Docker), `s8360_rel`. "
            "All tables below are generated by `scripts/hw7_build_metrics.py` from `reports/hw07/raw/`.", ""]
    (ROOT / "reports/hw07/METRICS.md").write_text("\n".join(head + part2() + part3() + part4() + part5() + part6()))
    print("wrote reports/hw07/METRICS.md")


if __name__ == "__main__":
    main()
