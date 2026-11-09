#!/usr/bin/env python3
"""HW9 Part 3.2-3.4: the filled threshold table, one false hit in full and the cost model, from reports/hw09/raw/threshold_sweep.json."""
import json
import re
import sys
from pathlib import Path

import yaml

from cache_svc.cost_model import COST_FALSE_HIT, COST_HIT, COST_MISS, total_cost

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports/hw09/raw"


def words(text: str) -> list[str]:
    return re.findall(r"[\w'-]+", text.lower())


def main() -> int:
    sweep = json.loads((RAW / "threshold_sweep.json").read_text())
    spec = yaml.safe_load((ROOT / "cache_cases.yaml").read_text())
    by_id = {c["id"]: c for c in spec["cases"]}
    seeds = sweep["seeds"]
    thresholds = sorted(sweep["thresholds"])

    print("3.2 threshold sweep (40 labeled cases: 20 should hit, 20 should miss; every miss ran the real agent pipeline)")
    print(f"{'threshold':>9} {'hit rate':>14} {'false-hit rate':>16} {'mean latency':>14} {'misses':>7} {'false hits':>11} {'total cost':>11}")
    table = {}
    for t in thresholds:
        s = sweep["thresholds"][t]["summary"]
        table[t] = {**s, "total_cost": total_cost(s["hits"], s["misses"], s["false_hits"])}
        print(f"{t:>9} {s['hits']:>3}/40 = {s['hit_rate']:>5.1%} {s['false_hits']:>4}/20 = {s['false_hit_rate']:>5.1%} {s['mean_latency_ms']:>11.0f} ms "
              f"{s['misses']:>7} {s['false_hits']:>11} ${table[t]['total_cost']:>9.4f}")

    print("\nnearest-seed similarity by category (it does not depend on the threshold)")
    cases = sweep["thresholds"][thresholds[0]]["cases"]
    stats = {}
    for category in ("exact_duplicate", "paraphrase", "superficially_similar", "unrelated"):
        sims = [c["similarity"] for c in cases if c["category"] == category]
        stats[category] = {"min": min(sims), "mean": round(sum(sims) / len(sims), 4), "max": max(sims)}
        print(f"  {category:22} min {min(sims):.4f}  mean {stats[category]['mean']:.4f}  max {max(sims):.4f}")

    print("\nper threshold: which labeled cases went wrong")
    wrong = {}
    for t in thresholds:
        rows = sweep["thresholds"][t]["cases"]
        false_ids = [r["id"] for r in rows if r["false_hit"]]
        missed = [r["id"] for r in rows if r["missed_hit"]]
        wrong[t] = {"false_hits": false_ids, "missed_hits": missed}
        print(f"  {t}: false hits {false_ids or 'none'}; should-hit cases that missed {missed or 'none'}")

    chosen = min(thresholds, key=lambda t: (table[t]["total_cost"], -float(t)))
    print(f"\n3.4 cost model: miss ${COST_MISS} (one agent run), hit ${COST_HIT}, false hit/support ${COST_FALSE_HIT} (about {COST_FALSE_HIT / COST_MISS:.0f} misses)")
    for t in thresholds:
        s = table[t]
        print(f"  {t}: {s['misses']} misses x ${COST_MISS} + {s['hits']} hits x ${COST_HIT} + {s['false_hits']} false hits x ${COST_FALSE_HIT} = ${s['total_cost']:.4f}"
              + ("   <- cheapest" if t == chosen else ""))
    print("  which threshold is cheapest if a false hit costs N times a miss:")
    sensitivity = {}
    for ratio in (1, 3, 10, 30, 100, 300):
        costs = {t: table[t]["misses"] * COST_MISS + table[t]["hits"] * COST_HIT + table[t]["false_hits"] * COST_MISS * ratio for t in thresholds}
        best = min(thresholds, key=lambda t: (costs[t], -float(t)))
        sensitivity[ratio] = best
        print(f"    N = {ratio:>3}: {best}  (" + ", ".join(f"{t}: ${costs[t]:.2f}" for t in thresholds) + ")")
    print(f"  chosen threshold to ship: {chosen}")

    default = "0.85"
    candidates = [c for c in sweep["thresholds"][default]["cases"] if c["false_hit"] and c["category"] == "superficially_similar"]
    pick = max(candidates, key=lambda c: c["similarity"]) if candidates else None
    detail = None
    if pick:
        case, seed = by_id[pick["id"]], seeds[by_id[pick["id"]]["confusable_with"]]
        a, b = words(case["query"]), words(seed["query"])
        detail = {"threshold": float(default), "case_id": case["id"], "incoming_query": case["query"], "cached_query": seed["query"], "similarity": pick["similarity"],
                  "cached_answer_returned": pick["answer"], "correct_answer": case["correct_answer"], "words_only_in_incoming": [w for w in a if w not in b],
                  "words_only_in_cached": [w for w in b if w not in a], "shared_words": len([w for w in a if w in b]), "incoming_words": len(a)}
        print(f"\n3.3 one false hit in full (threshold {default}, case {case['id']})")
        print(f"  incoming query : {case['query']}")
        print(f"  cached query   : {seed['query']}")
        print(f"  similarity     : {pick['similarity']:.4f} (>= {default}, so the cache answered)")
        print(f"  cached answer returned : {pick['answer']}")
        print(f"  correct answer         : {case['correct_answer']}")
        print(f"  the two questions share {detail['shared_words']} of {detail['incoming_words']} words; they differ only in {detail['words_only_in_incoming']} vs {detail['words_only_in_cached']}")

    (RAW / "sweep_analysis.json").write_text(json.dumps({"table": table, "category_similarity": stats, "wrong_cases": wrong, "chosen_threshold": chosen,
                                                         "sensitivity_best_threshold_by_cost_ratio": sensitivity, "false_hit_in_full": detail}, indent=2))
    print("\nsaved reports/hw09/raw/sweep_analysis.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
