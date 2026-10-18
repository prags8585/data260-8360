
import logging
from pathlib import Path

import file_memory as fm
from src.model_client import ModelClient

log = logging.getLogger("file_memory_agent")


class FileMemoryAgent:
    def __init__(self, llm=None, agent_path: Path = fm.AGENT_PATH, memory_path: Path = fm.MEMORY_PATH):
        self.llm = llm or ModelClient("qwen3:8b", 0.0, num_predict=160)
        self.agent_path, self.memory_path = agent_path, memory_path
        self.history: list[tuple[str, str]] = []

    def system_prompt(self) -> str:
        return fm.build_system_prompt(fm.load_agent_md(self.agent_path), fm.load_memory_md(self.memory_path))

    def reply(self, text: str) -> str:
        command_output = fm.handle_command(text, self.llm, self.history, self.agent_path, self.memory_path)
        if command_output is not None:
            return command_output
        required, reason = fm.needs_consolidation(fm.load_memory_md(self.memory_path))
        if required:
            log.info("auto-consolidating MEMORY.md: %s", reason)
            fm.cmd_compact(self.memory_path)
        messages = [("system", self.system_prompt())] + self.history[-10:] + [("user", text)]
        answer = self.llm.complete(messages).content.strip()
        self.history += [("user", text), ("assistant", answer)]
        return answer
