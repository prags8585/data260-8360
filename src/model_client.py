from dataclasses import dataclass
from typing import Optional

from langchain_ollama import ChatOllama


@dataclass
class CompletionResult:
    content: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ModelClient:

    def __init__(self, model: str = "qwen3:8b", temperature: float = 0.0):
        self.model = model
        self.temperature = temperature
        self._llm = ChatOllama(model=model, temperature=temperature, reasoning=False)

        self.turn_count = 0
        self.cumulative_input_tokens = 0
        self.cumulative_output_tokens = 0

    def complete(self, messages: list[tuple[str, str]], tools: Optional[list] = None) -> CompletionResult:
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
        )

    def stats(self) -> dict:
        return {
            "turn_count": self.turn_count,
            "cumulative_input_tokens": self.cumulative_input_tokens,
            "cumulative_output_tokens": self.cumulative_output_tokens,
            "cumulative_total_tokens": self.cumulative_input_tokens + self.cumulative_output_tokens,
        }
