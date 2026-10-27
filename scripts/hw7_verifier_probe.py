#!/usr/bin/env python3

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hw7_cases import CASES_BY_ID, oracle_correct  # noqa: E402
from src.model_client import ModelClient  # noqa: E402
from tool_agent import run_agent  # noqa: E402

RAW = ROOT / "reports/hw07/raw"


def main() -> None:
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    logging.basicConfig(level=logging.WARNING, force=True)
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===  verifier strictness probe: cases A and C without the required_tools guard, {trials} trials each, temperature 1.0")
    rows = []
    for case_id in ("A", "C"):
        case = CASES_BY_ID[case_id]
        for trial in range(trials):
            result = run_agent(case.prompt, model=ModelClient("qwen3:8b", 1.0, num_predict=400, seed=8360 + 500 + trial), min_tool_calls=case.min_tool_calls)
            check, oracle = case.verifier(result), oracle_correct(case_id, result["answer"])
            rows.append({"case": case_id, "trial": trial, "verifier_passed": check.passed, "oracle_correct": oracle, "false_rejection": (not check.passed) and oracle,
                         "assertion": check.assertion, "evidence": check.evidence, "tools": [c["tool"] for c in result["tool_calls"]],
                         "answer": (result["answer"] or "")[:300]})
            print(f"[case {case_id} trial {trial}] verifier={'PASS' if check.passed else 'REJECT'} oracle={'correct' if oracle else 'wrong'} tools={'>'.join(c['tool'] for c in result['tool_calls'])}", flush=True)
    summary = {"trials_per_case": trials, "runs": len(rows), "verifier_rejections": sum(not r["verifier_passed"] for r in rows),
               "false_rejections": sum(r["false_rejection"] for r in rows), "by_case": {c: {"rejected": sum(1 for r in rows if r["case"] == c and not r["verifier_passed"]),
               "false_rejections": sum(1 for r in rows if r["case"] == c and r["false_rejection"])} for c in ("A", "C")}}
    (RAW / "verifier_probe.json").write_text(json.dumps({"summary": summary, "runs": rows}, indent=2))
    print("\n" + json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
