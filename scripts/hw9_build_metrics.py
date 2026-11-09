#!/usr/bin/env python3
"""Builds reports/hw09/METRICS.md from the JSON files in reports/hw09/raw/."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports/hw09/raw"


def load(name):
    return json.loads((RAW / name).read_text())


def main() -> None:
    p2, sweep, ana, stale = load("part2_demo.json"), load("threshold_sweep.json"), load("sweep_analysis.json"), load("stale_demo.json")
    mine, val, final, demo = load("part4_mine.json"), load("part4_validation.json"), load("part4_final.json"), load("part4_demo.json")
    out = ["# METRICS - DATA-260 Homework 9", "",
           "Numbers come from the files in `reports/hw09/raw/` (one run each; model latencies vary from run to run, the hit/miss counts of the sweep do not).", "",
           "## Configuration", "", "| Value | Setting |", "|---|---|",
           "| SID4 / PORT_BASE / PREFIX / SEED / VERIFY_SEED | 8360 / 8260 / s8360 / 8360 / 268360 |",
           "| DOMAIN_ID / primary entity | 0 (Campus Course Catalogue and Enrolment) / Course |",
           "| Cache store | Redis Stack 7.4.7 (RediSearch 2.10.20) in Docker, host port 6382; FLAT vector index, FLOAT32, 384 dimensions, COSINE |",
           "| Embeddings | sentence-transformers/all-MiniLM-L6-v2 (normalised, CPU) |",
           "| Agent model | qwen3:8b via Ollama, temperature 0, seed 8360 |",
           f"| Labeled cases | `cache_cases.yaml`, 40 cases (20 should hit, 20 should miss), commit {sweep['cache_cases_commit'][:7]}, sha256 {sweep['cache_cases_sha256'][:16]}... |", ""]
    out += ["## Part 2 - 12-query demonstration (threshold 0.85)", "", "| Measure | Value |", "|---|---|",
            f"| Hit rate | {p2['stats']['hits']}/{p2['stats']['queries']} = {p2['hit_rate']:.1%} |",
            f"| Average latency, served from the cache | {p2['avg_latency_ms_hit']:.1f} ms |",
            f"| Average latency, agent pipeline (miss) | {p2['avg_latency_ms_miss']:.1f} ms |", ""]
    out += ["## Part 3 - threshold sweep (40 labeled cases)", "",
            "| Threshold | Hit rate | False-hit rate | Mean latency | Misses | False hits | Total cost |", "|---|---|---|---|---|---|---|"]
    for t, s in ana["table"].items():
        out.append(f"| {t} | {s['hits']}/40 = {s['hit_rate']:.1%} | {s['false_hits']}/20 = {s['false_hit_rate']:.1%} | {s['mean_latency_ms']:.0f} ms | {s['misses']} | {s['false_hits']} | ${s['total_cost']:.4f} |")
    c = sweep["costs"]
    out += ["", f"Cost model (fixed before the sweep): {c}. Chosen threshold: **{ana['chosen_threshold']}**. Cheapest threshold by false-hit cost ratio N (a false hit costs N misses): "
            + ", ".join(f"N={k}: {v}" for k, v in ana["sensitivity_best_threshold_by_cost_ratio"].items()) + ".", "",
            "| Category | Min similarity | Mean | Max |", "|---|---|---|---|"]
    out += [f"| {k} | {v['min']:.4f} | {v['mean']:.4f} | {v['max']:.4f} |" for k, v in ana["category_similarity"].items()]
    out += ["", "## Part 3 - stale answer", "", "| Step | Result |", "|---|---|",
            f"| `{stale['course']}` seats before / after the UPDATE | {stale['seats_before']} / {stale['seats_after']} |",
            f"| Plain semantic cache after the UPDATE | serves \"{stale['stale_hit']['answer']}\" (stale) |",
            f"| With the data-version check | \"{stale['after_invalidation']['answer']}\" (miss, stale entry invalidated, {stale['after_invalidation']['latency_ms']:.0f} ms) |",
            f"| Version check cost on a hit | {stale['second']['version_check_ms']} ms |", ""]
    r = {k: v["summary"] for k, v in final.items()}
    out += ["## Part 4 - self-improving system", "",
            f"Training: {mine['summary']['correct']}/{mine['summary']['questions']} correct without lessons; repeated failure patterns: " + ", ".join(f"{k} x{len(v)}" for k, v in mine["failures"].items()) + ".",
            f"Validation gate: {val['kept']} of {val['candidates']} candidate lessons kept.", "",
            "| Variant | Correct | Incorrect | Average attempts | Average latency |", "|---|---|---|---|---|"]
    out += [f"| {k} | {s['correct']}/{s['questions']} | {s['incorrect']} | {s['average_attempts']} | {s['average_latency_s']} s |" for k, s in r.items()]
    out += ["", f"Lesson reuse demo: lesson `{demo['lesson']['lesson_id']}` use_count after the later question = {demo['use_count_after']}.", "",
            "## Checks", "", "`python tests_hw9.py` (38 offline tests) and `python verify_hw09.py` (live smoke test, writes `verification.json`).", ""]
    (ROOT / "reports/hw09/METRICS.md").write_text("\n".join(out))
    print("METRICS lines:", len(out))


if __name__ == "__main__":
    main()
