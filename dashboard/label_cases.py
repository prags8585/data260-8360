"""A small page for hand-labelling the 20 drafts of eval_cases.json (HW10 Part 3.1). It shows the question, the draft and the catalogue, and writes
human_labels.csv. It never shows a judge score, and nothing here calls a model."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "eval_cases.json"
LABELS = ROOT / "human_labels.csv"
SCALE = {5: "Excellent: correct, complete, directly answers", 4: "Good: correct and useful, minor gap", 3: "Adequate: partly helpful, incomplete or one flaw",
         2: "Poor: mostly unhelpful, serious error or invented detail", 1: "Very poor: wrong, irrelevant or misleading"}


def read_labels() -> dict[str, dict]:
    if not LABELS.exists():
        return {}
    with LABELS.open() as handle:
        return {row["case_id"]: row for row in csv.DictReader(handle)}


def write_label(case_ids: list[str], case_id: str, label: int) -> None:
    rows = read_labels()
    rows[case_id] = {"case_id": case_id, "helpfulness_label": str(label), "labeled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with LABELS.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case_id", "helpfulness_label", "labeled_at"])
        for cid in case_ids:
            row = rows.get(cid, {})
            writer.writerow([cid, row.get("helpfulness_label", ""), row.get("labeled_at", "")])


def main() -> None:
    st.set_page_config(page_title="Label the drafts", layout="centered")
    cases = json.loads(CASES.read_text())["cases"]
    ids = [c["case_id"] for c in cases]
    labels = read_labels()
    done = sum(1 for cid in ids if labels.get(cid, {}).get("helpfulness_label", "").strip())
    st.title("Label the 20 Writer drafts")
    st.caption("Rate how helpful each draft is as an answer to its question (1-5, rubric in eval_rubric.md). Your labels are saved to human_labels.csv "
               "immediately. No judge score is shown here.")
    st.progress(done / len(ids), text=f"{done} of {len(ids)} labelled")
    case_id = st.selectbox("Case", ids, format_func=lambda c: f"{c}" + ("  (labelled)" if labels.get(c, {}).get("helpfulness_label", "").strip() else ""))
    case = next(c for c in cases if c["case_id"] == case_id)
    st.subheader("Question")
    st.write(case["question"])
    st.subheader("Writer draft")
    st.info(case["draft"])
    st.subheader("Catalogue (the only facts the Writer had)")
    st.table([{"code": c["courseCode"], "title": c["courseTitle"], "department": c["department"], "seats": c["seatsAvailable"], "instructor": c["instructorName"]}
              for c in case["facts"]["courses"]])
    current = labels.get(case_id, {}).get("helpfulness_label", "").strip()
    choice = st.radio("Helpfulness label", list(SCALE), index=list(SCALE).index(int(current)) if current else None, format_func=lambda s: f"{s} - {SCALE[s]}", key=f"label_{case_id}")
    if choice is not None and str(choice) != current:
        write_label(ids, case_id, int(choice))
        st.success(f"saved {case_id} = {choice}")


main()
