#!/usr/bin/env python3
"""Builds reports/hw10/METRICS.md from the JSON files in reports/hw10/raw/."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports/hw10/raw"


def load(name):
    p = RAW / name
    return json.loads(p.read_text()) if p.exists() else None


def jsonl(name):
    p = RAW / name
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


def main() -> None:
    evals, lat, req, trace, val = jsonl("part2_evals.jsonl"), load("latency_table.json"), load("latency_requests.json"), load("trace_examples.json"), load("judge_validation.json")
    out = ["# METRICS - DATA-260 Homework 10", "",
           "Numbers come from the files in `reports/hw10/raw/` (one run each; model latencies vary from run to run).", "",
           "## Configuration", "", "| Value | Setting |", "|---|---|",
           "| SID4 / PORT_BASE / PREFIX / SEED / VERIFY_SEED | 8360 / 8260 / s8360 / 8360 / 268360 |",
           "| DOMAIN_ID / primary entity | 0 (Campus Course Catalogue and Enrolment) / Course |",
           "| Pipeline | HW9 ingress + semantic cache (threshold 0.95) in front of the HW8 Planner, Writer, Reviewer on Kafka 3.8.0 |",
           "| Agents | qwen3:8b via Ollama, temperature 0, seed 8360 |",
           "| Judge | DeepEval GEval on qwen3:8b via Ollama, temperature 0, seed 8360, think off, 1-5 rubric, 90 s timeout per call, 2 attempts |",
           "| Trace file | kafka_state/traces/spans.jsonl (copied to reports/hw10/raw/spans.jsonl); trace_id = HW8 correlation_id |", ""]
    if evals:
        out += ["## Part 2 - evaluation of the pipeline (scores 1-5)", "", "| Case | Question | Plan | Writer draft | Final answer | Final - draft |", "|---|---|---|---|---|---|"]
        for i, r in enumerate(evals, 1):
            out.append(f"| c{i:02d} | {r['question']} | {r['plan_quality']['score']} | {r['writer_helpfulness']['score']} | {r['final_answer_helpfulness']['score']} | {r['final_vs_draft']['difference']} |")
        out.append("")
    if trace:
        out += ["## Part 4.2 - the three required traces", "", "| Trace | trace_id | Result |", "|---|---|---|"]
        for key, label in (("cache_hit", "Cache hit"), ("cache_miss", "Cache miss (success)"), ("failed", "Failed")):
            t = trace[key]
            out.append(f"| {label} | `{t['trace_id']}` | {t['result']} |")
        out.append("")
    if lat:
        out += ["## Part 4.3 - stage latency over 50 confirmed cache misses", "", "| Stage | p50 (ms) | p95 (ms) | % of cache-miss end-to-end |", "|---|---|---|---|"]
        out += [f"| {r['stage']} | {r['p50_ms']} | {r['p95_ms']} | {r['share_pct']} |" for r in lat["table"]]
        e = lat["end_to_end"]
        out += [f"| End-to-end (request span) | {e['p50_ms']} | {e['p95_ms']} | 100 |", "",
                f"Dominant contributor on the request path: **{lat['dominant']['stage']}** ({lat['dominant']['share_pct']}% of the end-to-end time). Cache-hit latency (separate metric, {lat['cache_hit']['n']} hits): "
                f"p50 {lat['cache_hit']['p50_ms']} ms, p95 {lat['cache_hit']['p95_ms']} ms. Candidate questions discarded because the cache answered: {len(req['discarded_cache_hits']) if req else 'n/a'}.", ""]
    if val:
        s, r = val["spearman"], val["repeatability"]
        out += ["## Part 3 - judge validation (20 drafts)", "", "| Measure | Value |", "|---|---|",
                f"| Spearman rho (human vs judge, run 1) | {s['rho']:.3f} (p = {s['p_value']:.4f}) |", f"| Mean absolute difference | {val['mean_absolute_difference']:.2f} |",
                f"| Bias (judge - human) | {val['bias']:+.2f} |", f"| Exact agreement / within one point | {val['exact_agreement']:.0%} / {val['within_one']:.0%} |",
                f"| Repeatability: cases with any change over 3 runs | {r['cases_with_any_change']} of {val['n']} |", f"| Mean / max absolute change between runs | {r['mean_abs_change']:.3f} / {r['max_abs_change']} |", "",
                f"Verdict: {val['verdict']}", ""]
    out += ["## Checks", "", "`python tests_hw10.py` (offline tests) and `python verify_hw10.py` (live smoke test, writes `verification.json`).", ""]
    (ROOT / "reports/hw10/METRICS.md").write_text("\n".join(out))
    print("METRICS lines:", len(out))


if __name__ == "__main__":
    main()
