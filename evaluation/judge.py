"""The LLM judge: DeepEval's GEval metric on a local model (qwen3:8b through Ollama), scored 1-5.

GEval is given explicit evaluation steps (so no extra step-generation call) and a 1-5 rubric; DeepEval returns (score - 1) / 4,
which is turned back into the 1-5 score here. Every call has a timeout and one retry, so a hung or missing judge cannot block a run."""
import asyncio
import os
import time
from dataclasses import dataclass

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")  # nothing is sent to DeepEval / Confident AI

from deepeval.metrics import GEval  # noqa: E402
from deepeval.metrics.g_eval import Rubric  # noqa: E402
from deepeval.models import DeepEvalBaseLLM  # noqa: E402
from deepeval.test_case import LLMTestCase, SingleTurnParams  # noqa: E402

JUDGE_MODEL = "qwen3:8b"
JUDGE_SETTINGS = {"model": JUDGE_MODEL, "temperature": 0.0, "seed": 8360, "num_predict": 400, "think": False, "timeout_s": 90, "max_attempts": 2,
                  "framework": "deepeval GEval", "scale": "1 (very poor) to 5 (excellent)"}

RUBRIC = [
    Rubric(score_range=(1, 1), expected_outcome="Very poor: wrong, irrelevant, empty or misleading."),
    Rubric(score_range=(2, 2), expected_outcome="Poor: mostly unhelpful, with a serious error or a major part missing."),
    Rubric(score_range=(3, 3), expected_outcome="Adequate: partly helpful, but incomplete or with a noticeable flaw."),
    Rubric(score_range=(4, 4), expected_outcome="Good: correct and useful, with a minor gap."),
    Rubric(score_range=(5, 5), expected_outcome="Excellent: correct, complete and directly answers the question."),
]

CRITERIA = {
    "plan_quality": {
        "name": "Plan Quality",
        "params": [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        "criteria": "Judge whether the plan (the actual output) is a useful plan for answering the question (the input) from a course catalogue.",
        "steps": ["Read the question and decide which catalogue facts are needed to answer it.",
                  "Check that the plan looks up exactly those facts and then answers from them.",
                  "Penalise plans that are vague, skip a needed lookup or plan to use information that a course catalogue does not hold.",
                  "Give an integer score from 1 (very poor) to 5 (excellent)."]},
    "writer_helpfulness": {
        "name": "Writer Helpfulness",
        "params": [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
        "criteria": "Judge whether the draft answer (the actual output) is accurate and useful for the question (the input), given the catalogue facts (the retrieval context).",
        "steps": ["Check that every number, name and course code in the draft agrees with the catalogue facts.",
                  "Check that the draft answers what the question asks, completely and directly.",
                  "If the question asks for something the catalogue facts do not contain, a draft that says so is better than one that invents an answer.",
                  "Give an integer score from 1 (very poor) to 5 (excellent)."]},
    "final_answer_helpfulness": {
        "name": "Final Answer Helpfulness",
        "params": [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
        "criteria": "Judge whether the final answer (the actual output) is helpful and relevant for the question (the input), given the catalogue facts (the retrieval context).",
        "steps": ["Check that the final answer addresses the question that was asked.",
                  "Check that its numbers and names agree with the catalogue facts.",
                  "A final answer that says no answer is available is not helpful, unless the question cannot be answered from the catalogue.",
                  "Give an integer score from 1 (very poor) to 5 (excellent)."]},
}


class LocalOllamaJudge(DeepEvalBaseLLM):
    """DeepEval model wrapper around the local Ollama server: temperature 0, fixed seed, no thinking, JSON output for the schema."""

    def __init__(self, settings: dict | None = None, host: str | None = None):
        self.settings = {**JUDGE_SETTINGS, **(settings or {})}
        self.host = host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        self.calls, self.call_ms = 0, []
        super().__init__(model=self.settings["model"])

    def load_model(self):
        from ollama import Client
        return Client(host=self.host, timeout=self.settings["timeout_s"])

    def get_model_name(self) -> str:
        return f"{self.settings['model']} (ollama, temperature {self.settings['temperature']}, seed {self.settings['seed']})"

    def supports_log_probs(self) -> bool:
        return False

    def generate(self, prompt: str, schema=None):
        last = None
        for attempt in range(1, self.settings["max_attempts"] + 1):
            t = time.perf_counter()
            try:
                response = self.model.chat(
                    model=self.settings["model"], messages=[{"role": "user", "content": prompt}], think=self.settings["think"],
                    format=schema.model_json_schema() if schema else None,
                    options={"temperature": self.settings["temperature"], "seed": self.settings["seed"], "num_predict": self.settings["num_predict"]})
                text = response["message"]["content"]
                self.calls += 1
                self.call_ms.append((time.perf_counter() - t) * 1000)
                return schema.model_validate_json(text) if schema else text
            except Exception as exc:  # timeout, connection error, malformed JSON: retry once, then give up
                last = exc
        raise RuntimeError(f"judge unavailable after {self.settings['max_attempts']} attempts: {type(last).__name__}: {last}") from last

    async def a_generate(self, prompt: str, schema=None):
        return await asyncio.to_thread(self.generate, prompt, schema)


@dataclass
class Judgement:
    criterion: str
    score: int | None
    reason: str
    error: str | None
    latency_ms: float


def make_metric(key: str, judge: LocalOllamaJudge) -> GEval:
    spec = CRITERIA[key]
    return GEval(name=spec["name"], evaluation_params=spec["params"], criteria=spec["criteria"], evaluation_steps=spec["steps"], rubric=RUBRIC,
                 model=judge, async_mode=False, threshold=0.5, _include_g_eval_suffix=False)


def judge_one(key: str, judge: LocalOllamaJudge, question: str, text: str, facts: str | None = None) -> Judgement:
    """One GEval score (an integer 1-5) with its reason; any failure becomes score None plus the error text, never an exception."""
    t = time.perf_counter()
    try:
        metric = make_metric(key, judge)
        case = LLMTestCase(input=question, actual_output=text, retrieval_context=[facts] if facts else None)
        normalised = metric.measure(case, _show_indicator=False)
        score = int(round(1 + 4 * float(normalised)))
        return Judgement(key, max(1, min(5, score)), (metric.reason or "").strip(), None, (time.perf_counter() - t) * 1000)
    except Exception as exc:
        return Judgement(key, None, "", f"{type(exc).__name__}: {exc}"[:300], (time.perf_counter() - t) * 1000)
