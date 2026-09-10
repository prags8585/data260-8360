#!/usr/bin/env python3

import json
import py_compile
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
checks = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as exc:
        ok, detail = False, f"exception: {exc}"
    checks.append({"name": name, "passed": ok, "detail": detail})


def file_exists(path):
    p = ROOT / path
    return p.exists(), f"{'found' if p.exists() else 'missing'}: {path}"


def python_syntax_ok(path):
    p = ROOT / path
    try:
        py_compile.compile(str(p), doraise=True)
        return True, f"valid Python syntax: {path}"
    except py_compile.PyCompileError as exc:
        return False, str(exc)


def node_syntax_ok(path):
    p = ROOT / path
    result = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
    return result.returncode == 0, result.stderr.strip() or "valid JS syntax"


def json_valid(path):
    p = ROOT / path
    try:
        json.loads(p.read_text())
        return True, f"valid JSON: {path}"
    except Exception as exc:
        return False, str(exc)


# --- Part 1: HTML/JS/Docker ---
check("index.html exists", lambda: file_exists("index.html"))
check("style.css exists", lambda: file_exists("style.css"))
check("script.js exists", lambda: file_exists("script.js"))
check("script.js valid syntax", lambda: node_syntax_ok("script.js"))
check("DOMAIN_SCHEMA.md exists", lambda: file_exists("DOMAIN_SCHEMA.md"))
check("Dockerfile exists", lambda: file_exists("Dockerfile"))
check(
    "index.html contains required form",
    lambda: (
        'id="courseForm"' in (ROOT / "index.html").read_text()
        and 'type="email"' in (ROOT / "index.html").read_text()
        and 'type="checkbox"' in (ROOT / "index.html").read_text(),
        "form/email/checkbox elements present",
    ),
)

# --- Part 2: Agentic AI ---
check("agents_demo.py exists", lambda: file_exists("agents_demo.py"))
check("agents_demo.py valid syntax", lambda: python_syntax_ok("agents_demo.py"))

# --- Part 3: Non-determinism ---
check("run_nondeterminism.py exists", lambda: file_exists("run_nondeterminism.py"))
check("run_nondeterminism.py valid syntax", lambda: python_syntax_ok("run_nondeterminism.py"))
check(
    "nondeterminism_input.json exists and valid",
    lambda: json_valid("reports/hw01/cases/nondeterminism_input.json"),
)
check("40 raw run records saved", lambda: (
    len(json.loads((ROOT / "reports/hw01/raw/nondeterminism_runs.json").read_text())) == 40,
    "reports/hw01/raw/nondeterminism_runs.json",
))
check("nondeterminism_runs.csv exists", lambda: file_exists("reports/hw01/raw/nondeterminism_runs.csv"))
check("nondeterminism_summary.json exists and valid", lambda: json_valid("reports/hw01/raw/nondeterminism_summary.json"))
check("METRICS.md exists", lambda: file_exists("reports/hw01/METRICS.md"))

# --- Part 4: Model client / token accounting ---
check("src/model_client.py exists", lambda: file_exists("src/model_client.py"))
check("src/model_client.py valid syntax", lambda: python_syntax_ok("src/model_client.py"))
check(
    "ModelClient defines complete(messages, tools=None)",
    lambda: (
        "def complete(self, messages" in (ROOT / "src/model_client.py").read_text()
        and "tools" in (ROOT / "src/model_client.py").read_text(),
        "signature check on src/model_client.py",
    ),
)
check("hw1_client.py exists", lambda: file_exists("hw1_client.py"))
check("hw1_client.py valid syntax", lambda: python_syntax_ok("hw1_client.py"))
check("AGENT.md exists", lambda: file_exists("AGENT.md"))
check("README.md exists", lambda: file_exists("README.md"))
check(
    "README.md answers all 4 conceptual questions",
    lambda: (
        all(
            phrase in (ROOT / "README.md").read_text()
            for phrase in ["resent with every turn", "system prompt", "input tokens grow", "context window"]
        ),
        "keyword check on README.md",
    ),
)

# --- Repository-level deliverables ---
check("RUN_LOG.txt exists and non-empty", lambda: (
    (ROOT / "reports/hw01/RUN_LOG.txt").exists() and (ROOT / "reports/hw01/RUN_LOG.txt").stat().st_size > 0,
    "reports/hw01/RUN_LOG.txt",
))
check("report.pdf exists", lambda: file_exists("reports/hw01/report.pdf"))
check("AI_USE.md exists", lambda: file_exists("reports/hw01/AI_USE.md"))

# --- Environment checks ---
check("Python 3.11/3.12 available", lambda: (
    sys.version_info[:2] in [(3, 11), (3, 12)],
    f"running under Python {sys.version.split()[0]}",
))


def ollama_model_pulled():
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    return "qwen3:8b" in result.stdout, result.stdout.strip().splitlines()[0] if result.stdout else "ollama list failed"


check("qwen3:8b pulled in Ollama", ollama_model_pulled)


passed = sum(1 for c in checks if c["passed"])
failed = len(checks) - passed

output = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "checks": checks,
    "passed": passed,
    "failed": failed,
    "total": len(checks),
    "overall": "PASS" if failed == 0 else "FAIL",
}

out_path = ROOT / "reports/hw01/verification.json"
out_path.write_text(json.dumps(output, indent=2))

print(f"{passed}/{len(checks)} checks passed.")
for c in checks:
    status = "OK  " if c["passed"] else "FAIL"
    print(f"  [{status}] {c['name']} -- {c['detail']}")
print(f"\nWrote {out_path}")

sys.exit(0 if failed == 0 else 1)
