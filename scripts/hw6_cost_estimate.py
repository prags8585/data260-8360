#!/usr/bin/env python3


import csv
import json
import sys
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "reports/hw06/raw"
INPUT_PER_M, OUTPUT_PER_M = 1.0, 5.0
CONVERSATIONS, TURNS = 10_000, 30
QUALITY_TOLERANCE = 0.5


def cost_row(s: dict) -> dict:
    in_tok = s["mean_prompt_tokens_per_turn"] + s["mean_overhead_prompt_tokens_per_turn"]
    out_tok = s["mean_completion_tokens_per_turn"] + s["mean_overhead_completion_tokens_per_turn"]
    turns = CONVERSATIONS * TURNS
    total_in, total_out = in_tok * turns, out_tok * turns
    chat_only = (s["mean_prompt_tokens_per_turn"] * turns * INPUT_PER_M
                 + s["mean_completion_tokens_per_turn"] * turns * OUTPUT_PER_M) / 1e6
    return {
        "setting": s["setting"], "mean_probe_quality": s["mean_probe_quality"],
        "input_tokens_per_turn": round(in_tok, 1), "output_tokens_per_turn": round(out_tok, 1),
        "total_input_tokens_M": round(total_in / 1e6, 2), "total_output_tokens_M": round(total_out / 1e6, 2),
        "input_cost_usd": round(total_in * INPUT_PER_M / 1e6, 2), "output_cost_usd": round(total_out * OUTPUT_PER_M / 1e6, 2),
        "total_cost_usd": round((total_in * INPUT_PER_M + total_out * OUTPUT_PER_M) / 1e6, 2),
        "chat_calls_only_cost_usd": round(chat_only, 2),
    }


def main() -> int:
    summary = json.loads((RAW / "memory_settings_summary.json").read_text())
    rows = [cost_row(s) for s in summary]
    top_quality = max(r["mean_probe_quality"] for r in rows)
    eligible = [r for r in rows if r["mean_probe_quality"] >= top_quality - QUALITY_TOLERANCE]
    best = min(eligible, key=lambda r: r["total_cost_usd"])
    worst = max(rows, key=lambda r: r["total_cost_usd"])
    for r in rows:
        r["role"] = "best" if r is best else ("worst" if r is worst else "")

    print(f"{CONVERSATIONS:,} conversations x {TURNS} turns = {CONVERSATIONS * TURNS:,} turns; "
          f"${INPUT_PER_M}/M input, ${OUTPUT_PER_M}/M output")
    print(f"{'Setting':<14}{'Quality':<9}{'In tok/turn':<13}{'Out tok/turn':<14}{'Input $':<10}{'Output $':<10}{'Total $':<10}Role")
    for r in rows:
        print(f"{r['setting']:<14}{r['mean_probe_quality']:<9}{r['input_tokens_per_turn']:<13}{r['output_tokens_per_turn']:<14}"
              f"{r['input_cost_usd']:<10}{r['output_cost_usd']:<10}{r['total_cost_usd']:<10}{r['role']}")
    print(f"\nbest  = {best['setting']}  (cheapest within {QUALITY_TOLERANCE} of top quality {top_quality})")
    print(f"worst = {worst['setting']}  (highest cost)")
    print(f"saving best vs worst: ${worst['total_cost_usd'] - best['total_cost_usd']:.2f} "
          f"({100 * (1 - best['total_cost_usd'] / worst['total_cost_usd']):.1f}%)")

    (RAW / "memory_cost_table.json").write_text(json.dumps(
        {"pricing": {"input_per_million_usd": INPUT_PER_M, "output_per_million_usd": OUTPUT_PER_M},
         "conversations": CONVERSATIONS, "turns_per_conversation": TURNS,
         "quality_tolerance": QUALITY_TOLERANCE, "best": best["setting"], "worst": worst["setting"], "rows": rows}, indent=2))
    with open(RAW / "memory_cost_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
