import json
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import jsonschema
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

log = logging.getLogger("tool_agent")

MAX_ITERATIONS = 8
MAX_FAILED_REPAIRS = 2

DOMAIN_SYSTEM_PROMPT = (
    "You are a course-catalogue assistant. You can only learn about courses by calling the provided tools; never guess. "
    "For multi-step questions call the tools you need one after another, using ids from earlier results, and give the final "
    "answer only after you have the facts. If a tool returns ok=false, tell the user what went wrong."
)

FAILURE_TYPES = ("malformed_arguments", "unknown_tool", "text_instead_of_tool", "lost_chain")


@dataclass
class Tool:
    name: str
    description: str
    schema: dict  # JSON schema for the arguments object
    fn: Callable[[dict], str]  # returns a JSON string


class Toolbox:
    """A set of tools: JSON-schema specs for the model, validation, and execution."""

    def __init__(self, tools: list[Tool]):
        self.tools = {t.name: t for t in tools}

    def specs(self) -> list[dict]:
        return [{"name": t.name, "description": t.description, "parameters": t.schema} for t in self.tools.values()]

    def validate(self, name: Any, args: Any) -> tuple[str, str] | None:
        """Returns (failure_type, specific_problem) or None when the call is well formed."""
        if not isinstance(name, str) or name not in self.tools:
            return "unknown_tool", f"unknown tool {name!r}; available tools: {', '.join(self.tools)}"
        if not isinstance(args, dict):
            return "malformed_arguments", f"arguments for {name} must be a JSON object, got {type(args).__name__}"
        errors = sorted(jsonschema.Draft202012Validator(self.tools[name].schema).iter_errors(args), key=lambda e: list(e.path))
        if errors:
            e = errors[0]
            where = ".".join(str(p) for p in e.path)
            return "malformed_arguments", f"invalid arguments for {name}" + (f" at '{where}'" if where else "") + f": {e.message}"
        return None

    def execute(self, name: str, args: dict) -> str:
        return self.tools[name].fn(args)


def domain_toolbox(repo=None) -> Toolbox:
    """The three HW5 domain tools, executed through execute_tool (validation + safety rule + error envelope)."""
    import execute_tool as et

    def make(name: str, description: str, schema: dict) -> Tool:
        return Tool(name, description, schema, lambda args, _n=name: et.execute_tool(_n, args, repo=repo))

    return Toolbox([
        make("search_courses", "Search courses by title, code or department (case-insensitive substring). Returns id, code, title, department, seats, instructor.",
             {"type": "object", "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 100},
                                               "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
              "required": ["query"], "additionalProperties": False}),
        make("course_detail", "Full detail for ONE course by its integer id (description and instructor).",
             {"type": "object", "properties": {"course_id": {"type": "integer", "minimum": 1}},
              "required": ["course_id"], "additionalProperties": False}),
        make("course_stats", "Aggregate: number of courses and total seats per department or per instructor.",
             {"type": "object", "properties": {"group_by": {"type": "string", "enum": ["department", "instructor"]}},
              "required": ["group_by"], "additionalProperties": False}),
    ])


def _emit(path: Path | None, record: dict) -> None:
    if path:
        with open(path, "a") as handle:
            handle.write(json.dumps(record) + "\n")


def _repair_message(failure: str, problem: str, made: int, required: int) -> str:
    if failure == "text_instead_of_tool":
        return f"You answered without calling a tool, but this task needs data from the tools ({problem}). Call the right tool now."
    if failure == "lost_chain":
        return (f"The task is not finished: you made {made} of at least {required} required tool calls ({problem}). "
                "Call the next tool you need before answering.")
    return f"Your last tool call was invalid: {problem}. Call a valid tool with valid arguments."


def run_agent(user_input: str, model=None, toolbox: Toolbox | None = None, *, system_prompt: str = DOMAIN_SYSTEM_PROMPT,
              max_iterations: int = MAX_ITERATIONS, max_failed_repairs: int = MAX_FAILED_REPAIRS, min_tool_calls: int = 0,
              required_tools: dict[str, int] | None = None, repair: bool = True, log_path: Path | str | None = None, run_id: str | None = None, scenario: str = "") -> dict:
    """Run the loop. `min_tool_calls` is the number of tool calls the task needs and `required_tools` maps tool name -> how many
    successful calls the task's chain needs; a final answer before both are met is a repairable "lost chain" failure."""
    if model is None:
        from src.model_client import ModelClient
        model = ModelClient("qwen3:8b", 0.0)
    toolbox = toolbox or domain_toolbox()
    out = Path(log_path) if log_path else None
    run_id = run_id or uuid.uuid4().hex[:8]
    messages: list = [SystemMessage(system_prompt), HumanMessage(user_input)]
    invocations: list[dict] = []   # every executed tool call
    opportunities: list[dict] = []  # one per model response where a tool call was required
    failed_repairs, tokens_in, tokens_out = 0, 0, 0
    answer, stop_reason, iteration = None, "max_iterations", 0
    pending: dict | None = None  # the opportunity currently being repaired
    required_tools = required_tools or {}
    started = time.perf_counter()
    _emit(out, {"run_id": run_id, "scenario": scenario, "event": "start", "user_input": user_input, "min_tool_calls": min_tool_calls})

    while iteration < max_iterations:
        iteration += 1
        result = model.complete(messages, tools=toolbox.specs())
        tokens_in += result.input_tokens
        tokens_out += result.output_tokens
        calls = result.tool_calls
        unmet = {t: n - sum(1 for i in invocations if i["tool"] == t and i["ok"]) for t, n in required_tools.items()}
        unmet = {t: k for t, k in unmet.items() if k > 0}
        need_call = len(invocations) < min_tool_calls or bool(unmet)
        issue: tuple[str, str] | None = None
        if calls:
            for c in calls:
                issue = toolbox.validate(c["name"], c["args"])
                if issue:
                    break
        elif need_call:
            missing = ", ".join(f"{t} x{k} more" for t, k in unmet.items()) or f"{min_tool_calls - len(invocations)} more call(s)"
            issue = ("text_instead_of_tool", "no tool has been called yet") if not invocations else \
                    ("lost_chain", f"{len(invocations)} tool call(s) so far; this task still needs {missing}")
        final = not calls and issue is None

        if pending is None and (need_call or calls):  # a tool call was expected: this response is one reliability opportunity
            pending = {"iteration": iteration, "first_ok": issue is None, "failure_type": issue[0] if issue else None,
                       "problem": issue[1] if issue else None, "repair_attempted": False, "repaired": False,
                       "raw_call": calls[0] if calls else {"text": str(result.content)[:200]}}
            opportunities.append(pending)
            if issue is None:
                pending = None
        elif pending is not None:  # this response is the answer to a repair reprompt
            if issue is None:
                pending["repaired"], pending = True, None
            else:
                failed_repairs += 1

        if issue is not None:
            _emit(out, {"run_id": run_id, "event": "invalid", "iteration": iteration, "failure_type": issue[0], "problem": issue[1]})
            log.warning("run=%s iter=%d invalid response (%s): %s", run_id, iteration, issue[0], issue[1])
            if not repair:
                stop_reason = "invalid_call"
                break
            if failed_repairs >= max_failed_repairs:
                stop_reason = "repair_failed"
                break
            pending["repair_attempted"] = True
            if calls:
                messages.append(result.message)
                for c in calls:
                    messages.append(ToolMessage(json.dumps({"ok": False, "data": None, "error": issue[1]}), tool_call_id=c["id"] or c["name"]))
            else:
                messages.append(AIMessage(str(result.content)))
            messages.append(HumanMessage(_repair_message(issue[0], issue[1], len(invocations), min_tool_calls)))
            continue

        if final:
            answer, stop_reason = str(result.content).strip(), "final_answer"
            _emit(out, {"run_id": run_id, "event": "final", "iteration": iteration, "answer": answer})
            break

        messages.append(result.message)
        for c in calls:
            observation = toolbox.execute(c["name"], c["args"])
            ok = bool(json.loads(observation).get("ok", True)) if observation.startswith("{") else True
            invocations.append({"tool": c["name"], "input": c["args"], "ok": ok, "observation": observation})
            log.info("run=%s tool_call #%d %s %s -> ok=%s", run_id, len(invocations), c["name"], json.dumps(c["args"]), ok)
            _emit(out, {"run_id": run_id, "event": "tool_call", "iteration": iteration, "n": len(invocations), "tool": c["name"],
                        "input": c["args"], "ok": ok, "observation": observation[:400]})
            messages.append(ToolMessage(observation, tool_call_id=c["id"] or c["name"], name=c["name"]))

    summary = {
        "run_id": run_id, "answer": answer, "stop_reason": stop_reason, "iterations": iteration,
        "total_tool_calls": len(invocations), "tool_calls": invocations, "opportunities": opportunities,
        "failed_repairs": failed_repairs, "input_tokens": tokens_in, "output_tokens": tokens_out,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }
    _emit(out, {"run_id": run_id, "event": "stop", **{k: v for k, v in summary.items() if k not in ("tool_calls", "opportunities", "answer")}})
    log.info("run=%s stopped: %s after %d iteration(s); total tool calls: %d", run_id, stop_reason, iteration, len(invocations))
    return summary
