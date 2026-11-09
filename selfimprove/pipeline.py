import json
import time
from pathlib import Path

from selfimprove.answering import AnsweringAgent
from selfimprove.evaluator import EvaluatorAgent


def load_questions(path: str | Path) -> list[dict]:
    return json.loads(Path(path).read_text())


def run_question(item: dict, answering: AnsweringAgent, evaluator: EvaluatorAgent, *, repair: bool, max_attempts: int = 2,
                 forced_first: str | None = None) -> dict:
    """Answering Agent answers, Evaluator checks; with repair on, a REVISE result sends the feedback back for a second (last) attempt."""
    question = item["question"]
    t0 = time.perf_counter()
    attempts: list[dict] = []
    answer = answering.answer(question, attempt=1, forced=forced_first)
    evaluation = evaluator.evaluate(question, answer["answer"], 1)
    attempts.append({"answer": answer["answer"], "lessons_used": answer["lessons_used"], "evaluation": evaluation})
    while repair and evaluation["result"] == "REVISE" and len(attempts) < max_attempts:
        n = len(attempts) + 1
        answer = answering.answer(question, attempt=n, previous=answer["answer"], feedback=evaluation["feedback"])
        evaluation = evaluator.evaluate(question, answer["answer"], n)
        attempts.append({"answer": answer["answer"], "lessons_used": answer["lessons_used"], "evaluation": evaluation})
    return {"id": item["id"], "question": question, "attempts": attempts, "attempt_count": len(attempts), "final_answer": answer["answer"],
            "final_result": evaluation["result"], "final_failure_type": evaluation["failure_type"], "kind": evaluation["kind"],
            "latency_s": round(time.perf_counter() - t0, 2)}


def run_set(items: list[dict], answering: AnsweringAgent, evaluator: EvaluatorAgent, *, repair: bool, max_attempts: int = 2, log=None) -> list[dict]:
    results = []
    for item in items:
        result = run_question(item, answering, evaluator, repair=repair, max_attempts=max_attempts)
        results.append(result)
        if log:
            log(result)
    return results


def summarize(results: list[dict]) -> dict:
    n = len(results)
    correct = sum(r["final_result"] == "PASS" for r in results)
    return {"questions": n, "correct": correct, "incorrect": n - correct, "average_attempts": round(sum(r["attempt_count"] for r in results) / n, 2),
            "average_latency_s": round(sum(r["latency_s"] for r in results) / n, 2)}


def validation_decision(before: list[dict], after: list[dict]) -> dict:
    """4.3: keep a lesson only if the failing questions improve or stay as they are, nothing that was right turns wrong, and
    questions the catalogue cannot answer do not start receiving unsupported answers."""
    was = {r["id"]: r["final_result"] == "PASS" for r in before}
    now = {r["id"]: r["final_result"] == "PASS" for r in after}
    fixed = [i for i in was if not was[i] and now[i]]
    regressed = [i for i in was if was[i] and not now[i]]

    def unsupported(results: list[dict]) -> int:
        return sum(r["final_failure_type"] == "unsupported_answer" for r in results)

    failing_before, failing_after = sum(not v for v in was.values()), sum(not v for v in now.values())
    keep = not regressed and failing_after <= failing_before and unsupported(after) <= unsupported(before)
    return {"keep": keep, "fixed": fixed, "regressed": regressed, "failing_before": failing_before, "failing_after": failing_after,
            "unsupported_before": unsupported(before), "unsupported_after": unsupported(after)}
