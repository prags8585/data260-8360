#!/usr/bin/env python3

import csv
import json
import logging
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hw7_cases import CASES, oracle_correct, unsupported_claims  # noqa: E402
from reflexion import Budget, ReflectionStore, run_with_reflexion  # noqa: E402
from src.model_client import ModelClient  # noqa: E402
from tool_agent import run_agent  # noqa: E402

RAW = ROOT / "reports/hw07/raw"
SEED, TEMPERATURE = 8360, 1.0


def make_model(seed: int):
    return ModelClient("qwen3:8b", TEMPERATURE, num_predict=400, seed=seed)


def main() -> None:
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    logging.basicConfig(level=logging.WARNING, force=True)
    store_path = RAW / "reflections.jsonl"
    if store_path.exists():
        store_path.unlink()
    store = ReflectionStore(store_path)
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===  {trials} trials x {len(CASES)} cases x 2 loops, qwen3:8b temperature {TEMPERATURE}")
    runs, events = [], []
    for trial in range(trials):
        for case in CASES:
            seed = SEED + 1000 + trial * 10 + ord(case.id) - 65
            # ---- original loop (Part 2: tool loop + repair path, no verifier-driven retry)
            res = run_agent(case.prompt, model=make_model(seed), min_tool_calls=case.min_tool_calls, required_tools=case.required_tools,
                            scenario=f"orig_{case.id}_{trial}")
            check, oracle = case.verifier(res), oracle_correct(case.id, res["answer"])
            events.append({"mode": "original", "case": case.id, "trial": trial, "attempt": 0, "verifier_passed": check.passed,
                           "oracle_correct": oracle, "false_rejection": (not check.passed) and oracle, "assertion": check.assertion})
            runs.append({"mode": "original", "case": case.id, "trial": trial, "seed": seed, "success": check.passed, "oracle_correct": oracle,
                         "stop_reason": res["stop_reason"], "retries": 0, "unsupported_claims": len(unsupported_claims(res)),
                         "tool_calls": res["total_tool_calls"], "tokens": res["input_tokens"] + res["output_tokens"],
                         "latency_ms": res["latency_ms"], "repair_reprompts": sum(o["repair_attempted"] for o in res["opportunities"])})
            # ---- Reflexion loop (same seed for the first attempt, new seed per retry)
            rx = run_with_reflexion(case, lambda attempt, s=seed: make_model(s + 7 * attempt), user_id="hw7-student",
                                    run_id=f"{case.id}{trial:02d}", store=store, budget=Budget())
            for a in rx["attempts"]:
                o = oracle_correct(case.id, a["result"]["answer"])
                events.append({"mode": "reflexion", "case": case.id, "trial": trial, "attempt": a["attempt"], "verifier_passed": a["check"].passed,
                               "oracle_correct": o, "false_rejection": (not a["check"].passed) and o, "assertion": a["check"].assertion})
            fin = rx["final_result"]
            runs.append({"mode": "reflexion", "case": case.id, "trial": trial, "seed": seed, "success": rx["success"],
                         "oracle_correct": oracle_correct(case.id, rx["answer"]), "stop_reason": rx["stop_reason"], "retries": rx["retries"],
                         "unsupported_claims": len(unsupported_claims(fin)), "tool_calls": rx["tool_calls"], "tokens": rx["tokens"],
                         "latency_ms": rx["latency_ms"], "repair_reprompts": sum(o["repair_attempted"] for a in rx["attempts"] for o in a["result"]["opportunities"])})
            print(f"[trial {trial} case {case.id}] original: {'PASS' if check.passed else 'FAIL'} ({res['latency_ms']:.0f} ms) | "
                  f"reflexion: {rx['stop_reason']} retries={rx['retries']} ({rx['latency_ms']:.0f} ms)")

    def agg(mode: str) -> dict:
        rows = [r for r in runs if r["mode"] == mode]
        ev = [e for e in events if e["mode"] == mode]
        return {
            "runs": len(rows), "task_success": f"{sum(r['success'] for r in rows)}/{len(rows)}",
            "task_success_rate": round(sum(r["success"] for r in rows) / len(rows), 4),
            "unsupported_claims_per_run": round(statistics.mean(r["unsupported_claims"] for r in rows), 3),
            "runs_with_unsupported_claims": sum(r["unsupported_claims"] > 0 for r in rows),
            "retry_rate_runs_with_retry": round(sum(r["retries"] > 0 for r in rows) / len(rows), 4),
            "retries_per_run": round(statistics.mean(r["retries"] for r in rows), 3),
            "repair_reprompts_per_run": round(statistics.mean(r["repair_reprompts"] for r in rows), 3),
            "tool_calls_per_run": round(statistics.mean(r["tool_calls"] for r in rows), 2),
            "tokens_per_run": round(statistics.mean(r["tokens"] for r in rows), 1),
            "latency_ms_per_run": round(statistics.mean(r["latency_ms"] for r in rows), 1),
            "verifier_false_rejections": sum(e["false_rejection"] for e in ev), "verification_events": len(ev),
            "stop_reasons": {s: sum(r["stop_reason"] == s for r in rows) for s in sorted({r["stop_reason"] for r in rows})},
        }

    summary = {"trials_per_case": trials, "temperature": TEMPERATURE, "original": agg("original"), "reflexion": agg("reflexion")}
    (RAW / "reflexion_comparison.json").write_text(json.dumps({"summary": summary, "runs": runs, "verification_events": events}, indent=2))
    with open(RAW / "reflexion_runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(runs[0]))
        w.writeheader()
        w.writerows(runs)
    print("\n" + json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
