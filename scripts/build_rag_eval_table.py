#!/usr/bin/env python3
import json
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "reports/hw04/raw"
results = json.loads((RAW / "rag_results.json").read_text())

CONFIG_LABELS = {"A_no_rag": "No RAG", "B_basic_rag": "Basic RAG", "C_context_engineered": "Context-eng."}


def fmt(v):
    if v is None:
        return "n/a"
    return "yes" if v else "no"


print(f"{'Q':<4}{'Config':<14}{'Retrieval':<11}{'Answer':<8}{'Grounded':<10}{'Refused ok':<12}")
rows = []
for r in results:
    # No RAG never retrieves anything -- "correct_retrieval" doesn't apply,
    # not "no". rag.py's evaluate() didn't special-case this; fixed here
    # rather than re-running the LLM pipeline.
    correct_retrieval = None if not r["retrieved"] else r["correct_retrieval"]
    row = {
        "question_id": r["question_id"], "category": r["category"], "config": r["config"],
        "correct_retrieval": correct_retrieval, "correct_answer": r["correct_answer"],
        "grounded": r["grounded"], "refused_when_needed": r["refused_when_needed"],
    }
    rows.append(row)
    print(f"{r['question_id']:<4}{CONFIG_LABELS[r['config']]:<14}"
          f"{fmt(correct_retrieval):<11}{fmt(r['correct_answer']):<8}"
          f"{fmt(r['grounded']):<10}{fmt(r['refused_when_needed']):<12}")

(RAW / "rag_evaluation_table.json").write_text(json.dumps(rows, indent=2))

# --- summary metrics -------------------------------------------------------
by_config = {c: [r for r in results if r["config"] == c] for c in CONFIG_LABELS}


def rate(vals):
    vals = [v for v in vals if v is not None]
    return round(100 * sum(bool(v) for v in vals) / len(vals), 1) if vals else None


print("\n=== Summary by configuration ===")
print(f"{'Config':<14}{'Accuracy %':<12}{'Faithfulness %':<16}{'Format-compliance %':<20}{'Robustness (Q5/Q6 refusal) %'}")
summary = {}
for c, label in CONFIG_LABELS.items():
    recs = by_config[c]
    accuracy = rate([r["correct_answer"] for r in recs])
    faithfulness = rate([r["grounded"] for r in recs])
    format_compliance = rate(["[source" in r["answer"].lower() for r in recs if r["config"] == "C_context_engineered"]) if c == "C_context_engineered" else None
    robustness_recs = [r for r in recs if r["refused_when_needed"] is not None]
    robustness = rate([r["refused_when_needed"] for r in robustness_recs])
    summary[label] = {
        "accuracy_pct": accuracy, "faithfulness_pct": faithfulness,
        "format_compliance_pct": format_compliance, "robustness_pct": robustness,
    }
    print(f"{label:<14}{str(accuracy):<12}{str(faithfulness):<16}{str(format_compliance):<20}{str(robustness)}")

(RAW / "rag_summary_metrics.json").write_text(json.dumps(summary, indent=2))
print(f"\nSaved {RAW / 'rag_evaluation_table.json'} and {RAW / 'rag_summary_metrics.json'}")
