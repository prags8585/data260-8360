"""Part 3: comparing judge scores with human labels (Spearman, mean absolute difference) and the repeatability of the judge. Pure functions, no model calls."""
from itertools import combinations

from scipy.stats import spearmanr


def spearman(human: list[float], judge: list[float]) -> dict:
    """Spearman rank correlation with its p-value. When either side is constant the correlation is undefined: rho is None and the reason is given."""
    if len(set(human)) < 2 or len(set(judge)) < 2:
        return {"rho": None, "p_value": None, "note": "undefined: one of the two score sets is constant"}
    result = spearmanr(human, judge)
    return {"rho": float(result.statistic), "p_value": float(result.pvalue), "note": ""}


def agreement(human: list[int], judge: list[int]) -> dict:
    n = len(human)
    diffs = [j - h for h, j in zip(human, judge)]
    return {"n": n, "mean_absolute_difference": sum(abs(d) for d in diffs) / n, "bias": sum(diffs) / n,
            "exact_agreement": sum(d == 0 for d in diffs) / n, "within_one": sum(abs(d) <= 1 for d in diffs) / n,
            "max_absolute_difference": max(abs(d) for d in diffs)}


def repeatability(runs: list[list[int]]) -> dict:
    """runs[k][i] = score of run k on case i. Reports how often and by how much a case's score changes between runs."""
    n = len(runs[0])
    pair_changes = [[abs(a[i] - b[i]) for i in range(n)] for a, b in combinations(runs, 2)]
    flat = [d for pair in pair_changes for d in pair]
    changed = [i for i in range(n) if len({run[i] for run in runs}) > 1]
    spread = [max(run[i] for run in runs) - min(run[i] for run in runs) for i in range(n)]
    return {"runs": len(runs), "pairs": len(pair_changes), "cases_with_any_change": len(changed), "changed_cases": changed,
            "fraction_of_pair_scores_changed": sum(d > 0 for d in flat) / len(flat), "mean_abs_change": sum(flat) / len(flat), "max_abs_change": max(flat),
            "max_spread_across_runs": max(spread)}


def verdict(rho: float | None, mad: float, bias: float, repeat: dict, n: int) -> str:
    """The deployment-gating answer, from fixed thresholds that are stated here: rho >= 0.8, MAD <= 0.5, |bias| <= 0.5, no change between runs, and at least 100 labeled cases."""
    problems = []
    if rho is None or rho < 0.8:
        problems.append(f"rank agreement with the humans is {'undefined' if rho is None else f'{rho:.2f}'} (threshold 0.80)")
    if mad > 0.5:
        problems.append(f"the judge is off by {mad:.2f} points on average (threshold 0.50)")
    if abs(bias) > 0.5:
        problems.append(f"it is {'more generous' if bias > 0 else 'harsher'} than the humans by {abs(bias):.2f} points")
    if repeat["cases_with_any_change"] > 0:
        problems.append(f"{repeat['cases_with_any_change']} of {n} scores changed between identical runs")
    if n < 100:
        problems.append(f"only {n} labeled cases are far too few to set a deployment gate (at least 100 are needed)")
    return ("I would NOT trust this judge to gate a deployment yet: " + "; ".join(problems) + ".") if problems else \
        "The judge meets every threshold set above, so it may be used as one signal in a deployment gate, next to the extra evidence listed."
