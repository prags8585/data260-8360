

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Protocol

import execute_tool as et
from domain_tools import CourseRepo

log = logging.getLogger("agent")
DEFAULT_LOG = Path(__file__).resolve().parent / "agent_runs.jsonl"
MAX_STEPS = 6

SYSTEM_PROMPT = """You are a course-catalogue assistant. Answer using ONLY these tools:

1. search_courses(query: str, limit: int 1-50)   - find courses by title, code or department
2. course_detail(course_id: int)                  - full detail for one course id
3. course_stats(group_by: "department" | "instructor") - course counts and total seats

Reply with exactly ONE JSON object per turn and nothing else:
  {"action": "tool", "name": "<tool name>", "inputs": {...}}
  {"action": "final", "answer": "<your answer to the user>"}

Call a tool only when you need data. After a tool result arrives, either call another
tool or give the final answer. If a tool returns ok=false, explain that in your final answer."""


class Model(Protocol):
    def generate(self, messages: list[dict]) -> str: ...


class MockModel:
    """Scripted model for offline tests: returns the given replies in order,
    repeating the last one forever (so it can simulate a model that never stops)."""

    def __init__(self, replies: list[str]):
        self.replies, self.calls = replies, 0

    def generate(self, messages: list[dict]) -> str:
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return reply


class OllamaModel:
    """Local qwen3:8b via Ollama, JSON mode, temperature 0."""

    def __init__(self, model: str = "qwen3:8b"):
        from langchain_ollama import ChatOllama
        self.name = model
        self._llm = ChatOllama(model=model, temperature=0.0, reasoning=False, format="json")

    def generate(self, messages: list[dict]) -> str:
        reply = self._llm.invoke([(m["role"], m["content"]) for m in messages])
        return reply.content


def _append(path: Path, record: dict) -> None:
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def run_agent(user_input: str, model: Model, max_steps: int = MAX_STEPS, repo: CourseRepo | None = None,
              log_path: Path | str | None = DEFAULT_LOG, scenario: str = "") -> dict:
    run_id = uuid.uuid4().hex[:8]
    out = Path(log_path) if log_path else None
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_input}]
    tool_calls = 0
    answer, stop_reason, step = None, "max_steps", 0

    def emit(**fields):
        record = {"run_id": run_id, "scenario": scenario, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **fields}
        if out:
            _append(out, record)

    emit(event="start", user_input=user_input, max_steps=max_steps)
    while step < max_steps:
        step += 1
        raw = model.generate(messages)
        try:
            action = json.loads(raw)
            if not isinstance(action, dict):
                raise ValueError("reply is not a JSON object")
        except ValueError as exc:
            emit(event="step", step=step, kind="invalid_model_output", raw=raw[:300], error=str(exc))
            messages += [{"role": "assistant", "content": raw},
                         {"role": "user", "content": 'Invalid reply. Respond with exactly one JSON object as specified.'}]
            continue

        if action.get("action") == "final":
            answer = str(action.get("answer", ""))
            emit(event="step", step=step, kind="final", answer=answer)
            stop_reason = "final_answer"
            break

        if action.get("action") == "tool":
            name, inputs = action.get("name"), action.get("inputs", {})
            result_json = et.execute_tool(name, inputs, repo=repo)
            tool_calls += 1
            result = json.loads(result_json)
            emit(event="step", step=step, kind="tool_call", tool=name, input=inputs, result=result)
            if not result["ok"] and str(result["error"]).startswith(et.BLOCK_PREFIX):
                stop_reason, answer = "safety_block", result["error"]
                break
            messages += [{"role": "assistant", "content": raw},
                         {"role": "user", "content": f"Tool result: {result_json}"}]
            continue

        emit(event="step", step=step, kind="invalid_model_output", raw=raw[:300], error="unknown action")
        messages += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": 'Unknown action. Use "tool" or "final".'}]

    emit(event="stop", steps=step, tool_calls=tool_calls, stop_reason=stop_reason, answer=answer)
    log.info("run %s stopped: %s after %d step(s), %d tool call(s)", run_id, stop_reason, step, tool_calls)
    return {"run_id": run_id, "answer": answer, "steps": step, "tool_calls": tool_calls, "stop_reason": stop_reason}
