#!/usr/bin/env python3


import logging
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hw7_cases import CASES  # noqa: E402
from src.model_client import ModelClient  # noqa: E402
from tool_agent import run_agent  # noqa: E402

LOG = ROOT / "reports/hw07/raw/agent_tool_log.jsonl"
ERROR_CASE = ("E", "error recovery: nonexistent id", "Show me the full details of the course with id 99999.", 1, {})


def main() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s", "%H:%M:%S"))
    logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)
    logging.getLogger("tool_agent").setLevel(logging.INFO)
    if LOG.exists():
        LOG.unlink()
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')} ===  run_agent demo, qwen3:8b temperature 0, seed 8360")
    cases = [(c.id, c.title, c.prompt, c.min_tool_calls, c.required_tools) for c in CASES] + [ERROR_CASE]
    for case_id, title, prompt, min_calls, required in cases:
        print(f"\n[Task {case_id}] {title}\nprompt: {prompt}")
        model = ModelClient("qwen3:8b", 0.0, num_predict=400, seed=8360)
        result = run_agent(prompt, model=model, min_tool_calls=min_calls, required_tools=required, log_path=LOG, scenario=f"task_{case_id}")
        for n, call in enumerate(result["tool_calls"], 1):
            if not call["ok"]:
                print(f"tool observation #{n} ({call['tool']}): {call['observation']}")
        print(f"answer: {result['answer']}")
        print(f"stop_reason={result['stop_reason']}  iterations={result['iterations']}  total_tool_calls={result['total_tool_calls']}  "
              f"tokens={result['input_tokens']}+{result['output_tokens']}  latency={result['latency_ms']:.0f} ms")


if __name__ == "__main__":
    main()
