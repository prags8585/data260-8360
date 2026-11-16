#!/usr/bin/env python3
"""HW10 Part 3.2 / 3.3: runs the judge on the 20 frozen drafts and compares it with the hand-assigned human labels.

Guards (the assignment's ordering rules): it refuses to run unless eval_cases.json and human_labels.csv are COMMITTED and unchanged since, and all 20
labels are integers from 1 to 5. The judge is the same GEval Writer-Helpfulness metric as in Part 2 (qwen3:8b, temperature 0, seed 8360). Three runs
with these settings give the repeatability result; --sampling-check adds three runs with sampling on (temperature 0.7, no seed) as a supplementary check."""
import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

from evaluation.judge import JUDGE_SETTINGS, LocalOllamaJudge, judge_one
from evaluation.validation import agreement, repeatability, spearman, verdict
from tracing.spans import iso

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports/hw10/raw"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def frozen_commit() -> dict:
    """Both files must be tracked and have no uncommitted change; returns the commit that last touched them."""
    for name in ("eval_cases.json", "human_labels.csv"):
        if not git("ls-files", name):
            sys.exit(f"{name} is not committed yet: commit it BEFORE any judge score is computed (assignment 3.1).")
        if git("status", "--porcelain", "--", name):
            sys.exit(f"{name} has uncommitted changes: commit the final version before running the judge.")
    return {"commit": git("log", "-1", "--format=%H", "--", "eval_cases.json", "human_labels.csv"),
            "committed_at": git("log", "-1", "--format=%aI", "--", "eval_cases.json", "human_labels.csv")}


def load_labels(case_ids: list[str]) -> dict[str, int]:
    with (ROOT / "human_labels.csv").open() as handle:
        rows = {r["case_id"]: r["helpfulness_label"].strip() for r in csv.DictReader(handle)}
    labels = {}
    for cid in case_ids:
        value = rows.get(cid, "")
        if value not in {"1", "2", "3", "4", "5"}:
            sys.exit(f"human label for {cid} is {value!r}: every case needs a hand-assigned integer label from 1 to 5.")
        labels[cid] = int(value)
    return labels


def run_judge(cases: list[dict], settings: dict, label: str) -> list[dict]:
    judge = LocalOllamaJudge(settings)
    out = []
    for case in cases:
        j = judge_one("writer_helpfulness", judge, case["question"], case["draft"], json.dumps(case["facts"], separators=(",", ":"), ensure_ascii=False))
        if j.score is None:
            sys.exit(f"judge failed on {case['case_id']}: {j.error}")
        out.append({"case_id": case["case_id"], "score": j.score, "reason": j.reason, "latency_ms": round(j.latency_ms, 1)})
        print(f"  {label} {case['case_id']}: judge {j.score}  ({j.latency_ms / 1000:.1f}s)")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sampling-check", action="store_true")
    args = parser.parse_args()
    frozen = frozen_commit()
    doc = json.loads((ROOT / "eval_cases.json").read_text())
    cases = doc["cases"]
    human = load_labels([c["case_id"] for c in cases])
    print(f"eval_cases.json and human_labels.csv were committed in {frozen['commit'][:7]} at {frozen['committed_at']}; running the judge now ({iso(time.time())}).")

    runs = [run_judge(cases, JUDGE_SETTINGS, f"run {k}") for k in (1, 2, 3)]
    h = [human[c["case_id"]] for c in cases]
    scores = [[r["score"] for r in run] for run in runs]
    result = {"frozen_files": frozen, "judge_settings": JUDGE_SETTINGS, "n": len(cases), "spearman": spearman(h, scores[0]), "spearman_each_run": [spearman(h, s) for s in scores],
              **{k: v for k, v in agreement(h, scores[0]).items() if k != "n"}, "repeatability": repeatability(scores)}
    result["spearman"]["p_value"] = result["spearman"]["p_value"] if result["spearman"]["p_value"] is not None else float("nan")
    result["verdict"] = verdict(result["spearman"]["rho"], result["mean_absolute_difference"], result["bias"], result["repeatability"], len(cases))
    result["cases"] = [{"case_id": c["case_id"], "question": c["question"], "writer_brain": c["writer_brain"], "human": human[c["case_id"]],
                        "judge_run1": scores[0][i], "judge_run2": scores[1][i], "judge_run3": scores[2][i], "difference_run1": scores[0][i] - human[c["case_id"]],
                        "judge_reason_run1": runs[0][i]["reason"]} for i, c in enumerate(cases)]
    if args.sampling_check:
        sampling = {**JUDGE_SETTINGS, "temperature": 0.7, "seed": None}
        sampled = [[r["score"] for r in run_judge(cases, sampling, f"sampling {k}")] for k in (1, 2, 3)]
        result["sampling_check"] = {"settings": sampling, "scores": sampled, "repeatability": repeatability(sampled), **{f"vs_human_run{k + 1}": spearman(h, sampled[k]) for k in range(3)}}
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "judge_validation.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    with (RAW / "judge_per_case.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case_id", "human", "judge_run1", "judge_run2", "judge_run3"])
        writer.writerows([[c["case_id"], c["human"], c["judge_run1"], c["judge_run2"], c["judge_run3"]] for c in result["cases"]])
    s = result["spearman"]
    print(f"\nSpearman rho = {s['rho']}  (p = {s['p_value']})   MAD = {result['mean_absolute_difference']:.3f}   bias = {result['bias']:+.2f}   exact = {result['exact_agreement']:.0%}")
    print(f"repeatability over 3 runs: {result['repeatability']}")
    print(result["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
