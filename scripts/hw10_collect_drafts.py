#!/usr/bin/env python3
"""HW10 Part 3.1: collects the 20 Writer drafts for eval_cases.json and writes the EMPTY human_labels.csv.

The drafts come from the system's own Writer code (kafka_svc.brains.write_draft: the same function, model qwen3:8b, temperature 0, seed 8360 and live
MySQL catalogue that writer.py uses). 14 drafts use the LLM Writer; 6 use the Writer's rule brain (`writer.py --brain rule`), which ignores the question,
so that the 1-5 scale is exercised on clearly unhelpful drafts too. The case order is shuffled with a fixed seed. Nothing here scores anything:
human_labels.csv is created with an empty label column that a person fills in by hand."""
import csv
import json
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("CATALOGUE_SOURCE", "mysql")

from kafka_svc import config  # noqa: E402
from kafka_svc.brains import make_model, plan_llm, plan_rule, write_draft  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LLM_QUESTIONS = [
    "How many seats are available in DATA-245?",
    "Who teaches Machine Learning Foundations?",
    "Which course has the fewest available seats?",
    "How many courses does Dr. Samuel Okafor teach?",
    "What is the total number of seats in the Data Science department?",
    "List the courses taught by Dr. Marcus Lee.",
    "Which instructor teaches DATA-230?",
    "What time does DATA-245 meet?",
    "Is DATA-260 a difficult course?",
    "Which Computer Science course has the most seats?",
    "How many seats are available across all courses?",
    "Recommend a course for someone who likes databases.",
    "What are the prerequisites for DATA-230?",
    "Which department does ENGR-200 belong to?",
]
RULE_QUESTIONS = [
    "How many seats are available in CS-146?",
    "Who teaches DATA-260?",
    "Which department has the most available seats, and which course there has the most seats?",
    "How many courses does the Engineering department offer?",
    "Which department has the most available seats?",
    "What is the title of DATA-245?",
]


def main() -> int:
    model = make_model(json_mode=True)  # planner model (JSON output)
    writer_model = make_model()
    cases = []
    for question in LLM_QUESTIONS:
        plan, source = plan_llm(model, question)
        draft, facts = write_draft("llm", writer_model, question, plan)
        cases.append({"question": question, "writer_brain": "llm", "plan": plan, "plan_source": source, "draft": draft, "facts": facts})
        print(f"llm  | {question}\n     -> {draft}")
    for question in RULE_QUESTIONS:
        plan = plan_rule(question)
        draft, facts = write_draft("rule", None, question, plan)
        cases.append({"question": question, "writer_brain": "rule", "plan": plan, "plan_source": "rule", "draft": draft, "facts": facts})
        print(f"rule | {question}\n     -> {draft}")
    random.Random(config.SEED).shuffle(cases)
    for i, case in enumerate(cases, 1):
        case["case_id"] = f"e{i:02d}"
    doc = {"description": "20 Writer drafts from the s8360 course-catalogue system (HW8/HW9 Writer). Frozen before any judge score was computed.",
           "writer_model": config.MODEL, "writer_settings": {"temperature": 0.0, "seed": config.SEED, "num_predict": 400, "catalogue_source": "mysql"},
           "collected_with": "scripts/hw10_collect_drafts.py", "cases": [{k: case[k] for k in ("case_id", "question", "writer_brain", "plan", "plan_source", "draft", "facts")} for case in cases]}
    (ROOT / "eval_cases.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    path = ROOT / "human_labels.csv"
    if path.exists() and any(row.get("helpfulness_label", "").strip() for row in csv.DictReader(path.open())):
        print("human_labels.csv already has labels - left untouched")
    else:
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["case_id", "helpfulness_label", "labeled_at"])
            writer.writerows([[case["case_id"], "", ""] for case in cases])
    print(f"wrote eval_cases.json ({len(cases)} drafts) and human_labels.csv (labels empty)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
