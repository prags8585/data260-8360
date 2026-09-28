# AI_USE.md — DATA-260 Homework 4

## 1. What did you use an AI assistant for, and what did you do yourself?

I decided the React app would be a separate email/password login from the existing HW3 Bootstrap
demo, and directed the CRUD flow (Home/Create/Update/Delete, plus a Sign Up flow I asked for after Part 2 so I'd have a way to prove new users actually land in MySQL). For Part 2, I chose to keep the benchmark data for Part 3 in its own tables rather than growing the graded `courses` table to 5,000 rows. For Part 3, I picked the related entit (course reviews) and asked for the index to be tied directly to the N+1 fix's own query rather than an unrelated column. For Part 4, I used AI to reused the HW3 domain corpus and asked for the six questions to be genuinely answerable/unanswerable from that corpus rather than generic examples.
also, Used AI to pickup and create metric, run_log, and verification file for my homework.

## 2. One AI-produced output that was wrong/unsuitable, or one thing you independently verified

`rag.py`'s `evaluate()` function scores `correct_retrieval` by checking whether the expected source file shows up in that run's retrieved chunks — but Claude wrote it the same way for all three configurations, including **No RAG**, which by design never calls `retrieve()` at all. The result: every No RAG row printed `correct_retrieval = no`, as if it had tried and failed to retrieve the right document, when it never attempted retrieval in the first place. "No" and "not applicable" were being conflated.

## 3. How you detected the problem or verified the result

I noticed it reading the printed evaluation table from `scripts/build_rag_eval_table.py` against what `no_rag()` actually does in `rag.py` — it sends the question straight to the LLM with no `retrieve()` call, so its `retrieved` list is always empty. A retrieval column that reads "no" for every No RAG row regardless of question is a tell that the check isn't measuring what it claims to.

## 4. What you changed and why it works now

Instead of editing `evaluate()` in `rag.py` and re-running the full 18-call LLM pipeline again, the fix went into `scripts/build_rag_eval_table.py`: it now overrides `correct_retrieval` to `None` whenever a saved record's `retrieved` list is empty, before printing or saving the table. Re-running just that script confirmed every No RAG row now reads `n/a` for retrieval across all six questions, while Basic RAG's and Context-engineered RAG's real retrieval results are untouched. The corrected table is what's saved in `reports/hw04/raw/rag_evaluation_table.json` and checked by `verify_hw04.py`.

## 5. Used AI to push code into my Github repo easily.