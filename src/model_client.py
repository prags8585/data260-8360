from dataclasses import dataclass, field
from typing import Any, Optional

from langchain_ollama import ChatOllama


@dataclass
class CompletionResult:
    content: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    tool_calls: list[dict] = field(default_factory=list)  # HW7: [{"id": ..., "name": ..., "args": {...}}]
    message: Any = None  # HW7: the raw AIMessage, so an agent loop can append it to the history


class ModelClient:

    def __init__(self, model: str = "qwen3:8b", temperature: float = 0.0,
                 num_predict: Optional[int] = None, json_mode: bool = False,
                 seed: Optional[int] = None, num_ctx: Optional[int] = None):
        self.model = model
        self.temperature = temperature
        extra = {}
        if num_predict:
            extra["num_predict"] = num_predict
        if json_mode:
            extra["format"] = "json"
        if seed is not None:
            extra["seed"] = seed
        if num_ctx:
            extra["num_ctx"] = num_ctx
        self._llm = ChatOllama(model=model, temperature=temperature, reasoning=False, **extra)

        self.turn_count = 0
        self.cumulative_input_tokens = 0
        self.cumulative_output_tokens = 0

    def complete(self, messages: list, tools: Optional[list] = None) -> CompletionResult:
        """`messages` may mix (role, text) tuples and LangChain message objects
        (HW7: ToolMessage / AIMessage with tool_calls); `tools` are JSON-schema function specs."""
        llm = self._llm.bind_tools(tools) if tools else self._llm
        response = llm.invoke(messages)

        usage = response.usage_metadata or {}
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

        self.turn_count += 1
        self.cumulative_input_tokens += input_tokens
        self.cumulative_output_tokens += output_tokens

        return CompletionResult(
            content=response.content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            tool_calls=[{"id": c.get("id"), "name": c["name"], "args": c["args"]} for c in (response.tool_calls or [])],
            message=response,
        )

    def stats(self) -> dict:
        return {
            "turn_count": self.turn_count,
            "cumulative_input_tokens": self.cumulative_input_tokens,
            "cumulative_output_tokens": self.cumulative_output_tokens,
            "cumulative_total_tokens": self.cumulative_input_tokens + self.cumulative_output_tokens,
        }
