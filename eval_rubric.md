# Human labeling rubric - HW10 Part 3

Rate each of the 20 Writer drafts in `eval_cases.json` by hand, from 1 to 5, in `human_labels.csv` (column `helpfulness_label`).
Do not use an LLM to produce or suggest labels, and do not change a label after you have seen any judge score.

**What you rate:** how helpful the draft is as an answer to its question, for a student using the course catalogue. Check the draft against the
catalogue table that is shown with the case (six courses: code, title, department, seats available, instructor). The catalogue holds nothing else:
no meeting times, rooms, prerequisites, tuition or course content, so an answer that gives those invents them.

| Label | Meaning |
|---|---|
| 5 | Excellent: correct, complete, and directly answers the question. |
| 4 | Good: correct and useful, with a minor gap (a little extra or missing detail). |
| 3 | Adequate: partly helpful, but incomplete or with a noticeable flaw. |
| 2 | Poor: mostly unhelpful, with a serious error, an invented detail, or a major part missing. |
| 1 | Very poor: wrong, irrelevant, or misleading. |

The judge uses the same 1-5 scale, so the two sets of scores can be compared directly.

**To label:** `streamlit run dashboard/label_cases.py` (it writes `human_labels.csv` for you and never shows a judge score), or edit the CSV by hand.
