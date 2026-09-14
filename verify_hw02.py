#!/usr/bin/env python3

import json
import py_compile
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SID4 = 8360
PORT_BASE = 8000 + (SID4 % 900)
SEED = SID4
VERIFY_SEED = 260000 + SID4
MODEL = "qwen3:8b"

checks = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as exc:
        ok, detail = False, f"exception: {exc}"
    checks.append({"name": name, "passed": ok, "detail": detail})
    status = "OK  " if ok else "FAIL"
    print(f"  [{status}] {name} -- {detail}", flush=True)


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


def json_valid(path):
    p = ROOT / path
    try:
        json.loads(p.read_text())
        return True, f"valid JSON: {path}"
    except Exception as exc:
        return False, str(exc)

check("main.py exists", lambda: file_exists("main.py"))
check("main.py valid syntax", lambda: python_syntax_ok("main.py"))
check("templates/index.html exists", lambda: file_exists("templates/index.html"))
check("static/style.css exists", lambda: file_exists("static/style.css"))
check("static/script.js exists", lambda: file_exists("static/script.js"))

def fastapi_smoke_test():
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT_BASE)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        deadline = time.time() + 15
        up = False
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", PORT_BASE), timeout=0.5):
                    up = True
                    break
            except OSError:
                time.sleep(0.3)
        if not up:
            return False, f"server never bound to port {PORT_BASE} within 15s"

        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"http://127.0.0.1:{PORT_BASE}/"],
            capture_output=True, text=True, timeout=10,
        )
        code = result.stdout.strip()
        return code == "200", f"GET / -> HTTP {code} on port {PORT_BASE}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


check(f"FastAPI backend responds on PORT_BASE ({PORT_BASE})", fastapi_smoke_test)

check("agent_graph.py exists", lambda: file_exists("agent_graph.py"))
check("agent_graph.py valid syntax", lambda: python_syntax_ok("agent_graph.py"))
check("src/model_client.py exists", lambda: file_exists("src/model_client.py"))
check(
    "agent_graph.py routes LLM calls through src/model_client.py (not raw ChatOllama)",
    lambda: (
        "from src.model_client import ModelClient" in (ROOT / "agent_graph.py").read_text()
        and "ChatOllama" not in (ROOT / "agent_graph.py").read_text(),
        "import check on agent_graph.py",
    ),
)


def langgraph_smoke_test():
    tmp_input = ROOT / "_smoke_test_input.json"
    tmp_input.write_text(json.dumps({
        "title": "Smoke Test Course",
        "content": "A short throwaway course description used only to verify the "
                    "agent graph starts up, terminates, and returns a schema-valid result.",
    }))
    try:
        result = subprocess.run(
            [sys.executable, "agent_graph.py", "--input", str(tmp_input), "--temperature", "0.7", "--ceiling", "6"],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return False, f"exited with code {result.returncode}: {result.stderr[-300:]}"
        if "FINALIZED (Publish)" not in result.stdout:
            return False, "graph did not reach a finalized state (hung or errored before publishing)"

        publish_block = result.stdout.split("FINALIZED (Publish)")[-1]
        json_text = publish_block[publish_block.index("{"):publish_block.index("}", publish_block.index("{")) + 1]
        published = json.loads(json_text)
        tags = published.get("tags", [])
        if len(tags) != 3:
            return False, f"published result has {len(tags)} tags, expected exactly 3: {tags}"
        return True, f"graph terminated and published exactly 3 tags: {tags}"
    finally:
        tmp_input.unlink(missing_ok=True)


check("LangGraph script terminates and returns exactly 3 tags", langgraph_smoke_test)

check("TagsSummarySchema defined in agent_graph.py", lambda: (
    "class TagsSummarySchema(BaseModel)" in (ROOT / "agent_graph.py").read_text(),
    "class definition check",
))
check("reports/hw02/cases/schema_input.json exists and valid", lambda: json_valid("reports/hw02/cases/schema_input.json"))
check("reports/hw02/cases/adversarial_input.json exists and valid", lambda: json_valid("reports/hw02/cases/adversarial_input.json"))
check("30-run classification results saved", lambda: (
    len(json.loads((ROOT / "reports/hw02/raw/schema_30runs.json").read_text())) == 30,
    "reports/hw02/raw/schema_30runs.json",
))
check("ceiling=2 (20 runs) results saved", lambda: (
    len(json.loads((ROOT / "reports/hw02/raw/ceiling_2_runs.json").read_text())) == 20,
    "reports/hw02/raw/ceiling_2_runs.json",
))
check("ceiling=10 (20 runs) results saved", lambda: (
    len(json.loads((ROOT / "reports/hw02/raw/ceiling_10_runs.json").read_text())) == 20,
    "reports/hw02/raw/ceiling_10_runs.json",
))
check("adversarial (5 runs) results saved", lambda: (
    len(json.loads((ROOT / "reports/hw02/raw/adversarial_5runs.json").read_text())) == 5,
    "reports/hw02/raw/adversarial_5runs.json",
))
check("part4_summary.json exists and valid", lambda: json_valid("reports/hw02/raw/part4_summary.json"))

# --- Repository-level deliverables ---
check("RUN_LOG.txt exists and non-empty", lambda: (
    (ROOT / "reports/hw02/RUN_LOG.txt").exists() and (ROOT / "reports/hw02/RUN_LOG.txt").stat().st_size > 0,
    "reports/hw02/RUN_LOG.txt",
))
check("METRICS.md exists", lambda: file_exists("reports/hw02/METRICS.md"))
check("AI_USE.md exists", lambda: file_exists("reports/hw02/AI_USE.md"))
check("report PDF exists", lambda: file_exists("reports/hw02/Pragada_HW2.pdf"))


def ollama_model_pulled():
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    return MODEL in result.stdout, result.stdout.strip().splitlines()[0] if result.stdout else "ollama list failed"


check(f"{MODEL} pulled in Ollama", ollama_model_pulled)


def git_commit_hash():
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return result.returncode == 0, result.stdout.strip() or result.stderr.strip()


commit_ok, commit_hash = git_commit_hash()

passed = sum(1 for c in checks if c["passed"])
failed = len(checks) - passed

output = {
    "homework": "HW2",
    "sid4": SID4,
    "commit_hash": commit_hash if commit_ok else None,
    "model": MODEL,
    "seed": SEED,
    "verify_seed": VERIFY_SEED,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "checks": checks,
    "passed": passed,
    "failed": failed,
    "total": len(checks),
    "overall": "PASS" if failed == 0 else "FAIL",
}

out_path = ROOT / "reports/hw02/verification.json"
out_path.write_text(json.dumps(output, indent=2))

print(f"\n{passed}/{len(checks)} checks passed.")
print(f"Wrote {out_path}")

sys.exit(0 if failed == 0 else 1)
