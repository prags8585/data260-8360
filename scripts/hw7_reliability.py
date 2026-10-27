#!/usr/bin/env python3

import csv
import json
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hw7_cases import CASES, unsupported_claims  # noqa: E402
from src.model_client import ModelClient  # noqa: E402
from tool_agent import FAILURE_TYPES, run_agent  # noqa: E402

RAW = ROOT / "reports/hw07/raw"
SEED, TEMPERATURE, ATTEMPTS = 8360, 0.7, 30


def main() -> None:
    logging.basicConfig(level=logging.WARNING, force=True)
    RAW.mkdir(parents=True, exist_ok=True)
    log_path = RAW / "reliability_tool_log.jsonl"
    if log_path.exists():
        log_path.unlink()
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===  {ATTEMPTS} attempts, qwen3:8b temperature {TEMPERATURE}, seeds {SEED}+i")
    attempts, opportunities = [], []
    for i in range(ATTEMPTS):
        case = CASES[i % len(CASES)]
        model = ModelClient("qwen3:8b", TEMPERATURE, num_predict=400, seed=SEED + i)
        result = run_agent(case.prompt, model=model, min_tool_calls=case.min_tool_calls, required_tools=case.required_tools,
                           log_path=log_path, scenario=f"attempt_{i + 1}_{case.id}")
        check = case.verifier(result)
        first_ok = sum(o["first_ok"] for o in result["opportunities"])
        after_ok = sum(o["first_ok"] or o["repaired"] for o in result["opportunities"])
        row = {"attempt": i + 1, "case": case.id, "seed": SEED + i, "stop_reason": result["stop_reason"],
               "opportunities": len(result["opportunities"]), "well_formed_first_try": first_ok, "well_formed_after_repair": after_ok,
               "total_tool_calls": result["total_tool_calls"], "tools": ">".join(c["tool"] for c in result["tool_calls"]),
               "verifier_passed": check.passed, "verifier_assertion": check.assertion,
               "unsupported_claims": len(unsupported_claims(result)), "input_tokens": result["input_tokens"],
               "output_tokens": result["output_tokens"], "latency_ms": result["latency_ms"]}
        attempts.append(row)
        for o in result["opportunities"]:
            opportunities.append({"attempt": i + 1, "case": case.id, "iteration": o["iteration"], "first_ok": o["first_ok"],
                                  "repaired": o["repaired"], "failure_type": o["failure_type"] or "", "problem": o["problem"] or ""})
        print(f"[{i + 1:2}/{ATTEMPTS}] case {case.id} seed={SEED + i} calls={result['total_tool_calls']} opp={len(result['opportunities'])} "
              f"first_ok={first_ok} after_repair={after_ok} stop={result['stop_reason']} verifier={'PASS' if check.passed else 'FAIL'} "
              f"({result['latency_ms']:.0f} ms)")

    total = len(opportunities)
    first = sum(o["first_ok"] for o in opportunities)
    after = sum(o["first_ok"] or o["repaired"] for o in opportunities)
    failures = Counter(o["failure_type"] for o in opportunities if o["failure_type"])
    repaired = Counter(o["failure_type"] for o in opportunities if o["failure_type"] and o["repaired"])
    summary = {
        "attempts": ATTEMPTS, "temperature": TEMPERATURE, "seed_base": SEED, "opportunities": total,
        "well_formed_before_repair": first, "well_formed_after_repair": after,
        "rate_before_repair": round(first / total, 4), "rate_after_repair": round(after / total, 4),
        "failures_by_type": {t: failures.get(t, 0) for t in FAILURE_TYPES},
        "repaired_by_type": {t: repaired.get(t, 0) for t in FAILURE_TYPES},
        "attempts_verified": sum(a["verifier_passed"] for a in attempts), "attempts_with_repair": sum(1 for a in attempts if a["well_formed_first_try"] < a["opportunities"]),
        "mean_latency_ms": round(sum(a["latency_ms"] for a in attempts) / ATTEMPTS, 1),
        "mean_tool_calls": round(sum(a["total_tool_calls"] for a in attempts) / ATTEMPTS, 2),
    }
    with open(RAW / "reliability_attempts.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(attempts[0]))
        w.writeheader()
        w.writerows(attempts)
    with open(RAW / "reliability_opportunities.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(opportunities[0]))
        w.writeheader()
        w.writerows(opportunities)
    (RAW / "reliability_summary.json").write_text(json.dumps({"summary": summary, "attempts": attempts, "opportunities": opportunities}, indent=2))
    print("\n" + json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
