#!/usr/bin/env python3


import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET_FILE, TARGET_FUNC = ROOT / "file_memory.py", "memory_health_report"
TEST_FILE, TEST_FUNC = ROOT / "tests_hw6.py", "test_memory_health_report"
FORBIDDEN_TEST_IMPORTS = {"requests", "httpx", "pymongo", "sqlalchemy", "ollama", "langchain_ollama", "src"}
SECRET_RE = re.compile(r"(api[_-]?key|secret|password)\s*=\s*['\"][^'\"]{6,}", re.IGNORECASE)


def find_function(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    return next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name), None)


def called_names(func: ast.FunctionDef) -> set[str]:
    return {n.func.id for n in ast.walk(func) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def check_function(func: ast.FunctionDef) -> list[tuple[str, bool, str]]:
    params = [a for a in func.args.args + func.args.kwonlyargs if a.arg != "self"]
    untyped = [a.arg for a in params if a.annotation is None]
    length = func.end_lineno - func.lineno + 1
    calls = called_names(func)
    return [
        ("#5 type hints on every parameter and the return value", not untyped and func.returns is not None,
         f"untyped params: {untyped or 'none'}; return annotation: {ast.unparse(func.returns) if func.returns else 'MISSING'}"),
        ("#6 function is 30 lines or fewer", length <= 30, f"{length} lines"),
        ("#7 snake_case function name", bool(re.fullmatch(r"[a-z_][a-z0-9_]*", func.name)), func.name),
        ("#7 no print() inside the function", "print" not in calls, f"calls: {sorted(calls)}"),
        ("#11 no eval()/exec()", not ({"eval", "exec"} & calls), "none called"),
    ]


def check_module() -> list[tuple[str, bool, str]]:
    source = TARGET_FILE.read_text()
    test_source = TEST_FILE.read_text()
    test_tree = ast.parse(test_source)
    imports = {n.names[0].name.split(".")[0] for n in ast.walk(test_tree) if isinstance(n, ast.Import)}
    imports |= {(n.module or "").split(".")[0] for n in ast.walk(test_tree) if isinstance(n, ast.ImportFrom)}
    return [
        ("#7 module has no print() call (library module)", not re.search(r"^\s*print\(", source, re.M), TARGET_FILE.name),
        ("#8 an assert-based test exists for the function",
         find_function(test_tree, TEST_FUNC) is not None and "assert" in test_source, f"{TEST_FILE.name}::{TEST_FUNC}"),
        ("#8 the test file imports nothing that needs network/DB/LLM", not (imports & FORBIDDEN_TEST_IMPORTS),
         f"forbidden imports found: {sorted(imports & FORBIDDEN_TEST_IMPORTS) or 'none'}"),
        ("#9 no hard-coded secrets in the module", not SECRET_RE.search(source), "pattern scan"),
        ("#10 file_memory.cmd_compact writes a backup before overwriting MEMORY.md",
         "copyfile(memory_path, backup)" in source and source.index("copyfile(memory_path, backup)") < source.index("memory_path.write_text(new_text"),
         "backup copy precedes write_text"),
    ]


def main() -> int:
    func = find_function(ast.parse(TARGET_FILE.read_text()), TARGET_FUNC)
    if func is None:
        print(f"function {TARGET_FUNC} not found")
        return 1
    print(f"Checking {TARGET_FILE.name}::{TARGET_FUNC} against AGENT.md (lines {func.lineno}-{func.end_lineno})")
    results = check_function(func) + check_module()
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} -- {detail}")
    passed = sum(ok for _, ok, _ in results)
    print(f"\n{passed}/{len(results)} AGENT.md checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
