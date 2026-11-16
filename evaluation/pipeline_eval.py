"""Part 2: join the Planner plan, Writer draft and Reviewer final answer by correlation_id and score them with the judge."""
import json
import time
from dataclasses import dataclass, field

from evaluation.judge import CRITERIA, JUDGE_SETTINGS, RUBRIC, Judgement, LocalOllamaJudge, judge_one
from tracing.spans import emit_span

NO_ANSWER = "No answer was returned: the Reviewer rejected the draft."


@dataclass
class JoinStore:
    """Messages from the tasks (plan), drafts and final topics, joined on correlation_id. Malformed messages are counted, never raised."""
    plans: dict = field(default_factory=dict)
    drafts: dict = field(default_factory=dict)
    finals: dict = field(default_factory=dict)
    skipped: int = 0

    KIND = {"tasks": "plans", "drafts": "drafts", "final": "finals"}

    def add(self, kind: str, body, produced_at: float | None = None, meta: dict | None = None) -> str | None:
        cid = body.get("correlation_id") if isinstance(body, dict) else None
        if not isinstance(cid, str) or not cid:
            self.skipped += 1
            return None
        required = {"plans": "plan", "drafts": "draft", "finals": "status"}[self.KIND[kind]]
        if required not in body:
            self.skipped += 1
            return None
        if body.get("test"):  # failure-test traffic of HW8 has no human-readable question; it is not evaluated
            self.skipped += 1
            return None
        getattr(self, self.KIND[kind]).setdefault(cid, {"body": body, "produced_at": produced_at, "meta": meta})
        return cid

    def complete(self, cid: str) -> bool:
        return cid in self.plans and cid in self.drafts and cid in self.finals

    def incomplete(self) -> list[str]:
        seen = set(self.plans) | set(self.drafts) | set(self.finals)
        return sorted(c for c in seen if not self.complete(c))


def plan_text(task: dict) -> str:
    return "\n".join(f"{i}. {step}" for i, step in enumerate(task.get("plan") or [], 1))


def facts_text(draft: dict) -> str:
    return json.dumps(draft.get("facts"), separators=(",", ":"), ensure_ascii=False)


def interpret(draft_score: int | None, final_score: int | None, final: dict, draft: dict) -> str:
    """The Final-vs-Draft interpretation, written from the facts of the run (deterministic text, not a model's opinion)."""
    if draft_score is None or final_score is None:
        return "Not comparable: at least one judge call failed."
    diff = final_score - draft_score
    same = final.get("answer") == draft.get("draft")
    if final.get("status") != "approved":
        return (f"The Reviewer rejected the draft, so there is no final answer (difference {diff:+d}). The Reviewer protected the user from a draft its "
                "checks consider wrong, but the user gets nothing.")
    if same and diff == 0:
        return ("No improvement, as expected: the Reviewer is a gate. It checks the draft and approves it unchanged, so the final answer is the "
                "draft and the two scores are the same. The final answer is only as good as the draft.")
    if same:
        return f"The final answer is word for word the draft, so the difference of {diff:+d} is judge noise, not an improvement by the Reviewer."
    return f"The final answer differs from the draft (difference {diff:+d})."


def judgement_dict(j: Judgement) -> dict:
    return {"score": j.score, "reason": j.reason, "error": j.error, "latency_ms": round(j.latency_ms, 1)}


def evaluate_trace(cid: str, task: dict, draft: dict, final: dict, judge: LocalOllamaJudge, deadline_s: float = 300.0, meta: dict | None = None) -> dict:
    """Scores one request with the four required criteria. Bounded: the judge has a timeout per call and the whole trace has a deadline."""
    started = time.time()
    question = draft.get("question") or task.get("question") or final.get("question") or ""
    facts = facts_text(draft)
    answer = final.get("answer") or NO_ANSWER
    results: dict[str, Judgement] = {}
    for key, text, ctx in (("plan_quality", plan_text(task), None), ("writer_helpfulness", draft.get("draft") or "", facts),
                           ("final_answer_helpfulness", answer, facts)):
        if time.time() - started > deadline_s:
            results[key] = Judgement(key, None, "", f"evaluation deadline of {deadline_s:g}s exceeded", 0.0)
            continue
        results[key] = judge_one(key, judge, question, text, ctx)
    finished = time.time()
    errors = {k: j.error for k, j in results.items() if j.error}
    record = {
        "trace_id": cid, "question": question, "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
        "judge": JUDGE_SETTINGS | {"model_name": judge.get_model_name()},
        "plan_quality": judgement_dict(results["plan_quality"]) | {"plan": task.get("plan"), "plan_source": task.get("plan_source")},
        "writer_helpfulness": judgement_dict(results["writer_helpfulness"]) | {"trace_id": cid, "draft": draft.get("draft")},
        "final_answer_helpfulness": judgement_dict(results["final_answer_helpfulness"]) | {"final_answer": final.get("answer"), "review_status": final.get("status")},
        "final_vs_draft": {"draft_score": results["writer_helpfulness"].score, "final_score": results["final_answer_helpfulness"].score},
        "errors": errors, "duration_ms": round((finished - started) * 1000, 1),
        "messages": {"plan": task, "draft": draft, "final": final},  # the original messages, so the evaluation can be reproduced
        # where each message came from (topic, partition, offset, producer timestamp) and the exact criteria text the judge was given
        "message_metadata": meta or {},
        "criteria": {key: {"name": spec["name"], "criteria": spec["criteria"], "evaluation_steps": spec["steps"]} for key, spec in CRITERIA.items()}
                    | {"rubric": [{"score": r.score_range[0], "meaning": r.expected_outcome} for r in RUBRIC]},
    }
    d, f = record["final_vs_draft"]["draft_score"], record["final_vs_draft"]["final_score"]
    record["final_vs_draft"]["difference"] = None if d is None or f is None else f - d
    record["final_vs_draft"]["interpretation"] = interpret(d, f, final, draft)
    emit_span(cid, "evaluation", started, finished, "error" if errors else "ok", "; ".join(f"{k}: {v}" for k, v in errors.items()) or None,
              service="evaluator", judge_calls=3, plan_quality=record["plan_quality"]["score"], writer_helpfulness=d, final_answer_helpfulness=f)
    return record
