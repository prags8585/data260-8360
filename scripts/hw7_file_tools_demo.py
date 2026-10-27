#!/usr/bin/env python3

import json
import logging
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import hw7_safety_gate_test  # noqa: E402

import file_tools as ft  # noqa: E402
from src.model_client import ModelClient  # noqa: E402
from tool_agent import run_agent  # noqa: E402

LOG = ROOT / "reports/hw07/raw/file_tools_agent_log.jsonl"
FILES = {
    "inventory.py": "def count_items(items):\n    return len(items)\n",
    "settings.py": "DEBUG = True\nTIMEOUT = 30\nRETRIES = 3\n",
    "report.py": "def render(rows):\n    return \"\\n\".join(rows)\n",
}
INSTRUCTION = ("Find the Python file in the sandbox that contains the word DEBUG and show me its full contents. Work in this order: first list the "
               "Python files with glob_files, then search them for DEBUG with search_in_files, then read the matching file with read_file.")


def main() -> int:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s", "%H:%M:%S"))
    logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)
    logging.getLogger("tool_agent").setLevel(logging.INFO)
    if LOG.exists():
        LOG.unlink()
    sandbox = Path(tempfile.mkdtemp(prefix="course_sandbox_"))
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===  file tools + safety gate, sandbox {sandbox}")
    try:
        print("\n(a) the six file tools, used directly")
        print("write_file  ->", json.dumps(ft.write_file("notes/todo.txt", "buy milk\nwrite report\nsubmit HW7\n", root=sandbox)))
        print("read_file(max_lines=2) ->", json.dumps(ft.read_file("notes/todo.txt", max_lines=2, root=sandbox)))
        print("edit_file   ->", json.dumps(ft.edit_file("notes/todo.txt", "write report", "write HW7 report", root=sandbox)))
        print("glob_files('**/*.txt') ->", json.dumps(ft.glob_files("**/*.txt", root=sandbox)))
        print("search_in_files('HW7', file_pattern='*.txt') ->", json.dumps(ft.search_in_files("HW7", "*.txt", root=sandbox)))
        print("bash('cat notes/todo.txt') ->", json.dumps(ft.bash("cat notes/todo.txt", root=sandbox)))
        print("bash('rm -rf notes') ->", json.dumps(ft.bash("rm -rf notes", root=sandbox)))
        shutil.rmtree(sandbox / "notes")

        print("\n(b) integration test: glob -> search -> read through run_agent()")
        for name, content in FILES.items():
            ft.write_file(name, content, root=sandbox)
        model = ModelClient("qwen3:8b", 0.0, num_predict=500, seed=8360)
        result = run_agent(INSTRUCTION, model=model, toolbox=ft.file_toolbox(sandbox), min_tool_calls=3,
                           required_tools={"glob_files": 1, "search_in_files": 1, "read_file": 1},
                           system_prompt="You are a file assistant. Use only the provided tools, one step at a time, and never guess file contents.",
                           log_path=LOG, scenario="file_tools_integration")
        order = [c["tool"] for c in result["tool_calls"]]
        found = "DEBUG = True" in (result["answer"] or "") and "settings.py" in (result["answer"] or "")
        print(f"answer: {result['answer']}")
        print(f"tool order: {' -> '.join(order)}  | total_tool_calls={result['total_tool_calls']}  stop_reason={result['stop_reason']}")
        print(f"integration test: {'PASS' if found and order[:3] == ['glob_files', 'search_in_files', 'read_file'] else 'CHECK'} "
              f"(file containing DEBUG = settings.py)")
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)

    print("\n(c) safety-gate test")
    return hw7_safety_gate_test.run("final")


if __name__ == "__main__":
    sys.exit(main())
