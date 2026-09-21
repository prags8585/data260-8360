#!/usr/bin/env python3
"""HW3 smoke test (make verify-hw03).

Starts the actual system and checks the basic things work. Behavioral
checks only (e.g. "did retrieval return the right number of chunks?"),
never exact model/embedding wording. Creates only temporary test files;
never modifies application code.
"""

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
MODEL = "sentence-transformers/all-MiniLM-L6-v2"

checks = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as exc:
        ok, detail = False, f"exception: {exc}"
    checks.append({"name": name, "passed": ok, "detail": detail})
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name} -- {detail}", flush=True)


def file_exists(path):
    p = ROOT / path
    return p.exists(), f"{'found' if p.exists() else 'missing'}: {path}"


def python_syntax_ok(path):
    try:
        py_compile.compile(str(ROOT / path), doraise=True)
        return True, f"valid Python syntax: {path}"
    except py_compile.PyCompileError as exc:
        return False, str(exc)


def json_valid(path):
    try:
        json.loads((ROOT / path).read_text())
        return True, f"valid JSON: {path}"
    except Exception as exc:
        return False, str(exc)


# --- Part 1: auth app files ---
check("auth.py exists", lambda: file_exists("auth.py"))
check("auth.py valid syntax", lambda: python_syntax_ok("auth.py"))
check("templates/login.html exists", lambda: file_exists("templates/login.html"))
check("templates/dashboard.html exists", lambda: file_exists("templates/dashboard.html"))
check("main.py wires in SessionMiddleware", lambda: (
    "SessionMiddleware" in (ROOT / "main.py").read_text() and "include_router(auth.router)" in (ROOT / "main.py").read_text(),
    "text check on main.py",
))


def fastapi_https_smoke_test():
    cert, key = ROOT / "certs/localhost-cert.pem", ROOT / "certs/localhost-key.pem"
    if not (cert.exists() and key.exists()):
        return False, "certs/localhost-{cert,key}.pem missing -- run the openssl command in README.md"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT_BASE),
         "--ssl-keyfile", str(key), "--ssl-certfile", str(cert)],
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

        login = subprocess.run(
            ["curl", "-sk", "-D", "-", "-o", "/dev/null", "-X", "POST",
             f"https://127.0.0.1:{PORT_BASE}/login", "-d", "username=karthik&password=data260"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        has_secure_cookie = all(attr in login.lower() for attr in ["secure", "httponly", "samesite"])
        goes_to_dashboard = "location: /dashboard" in login.lower()
        return has_secure_cookie and goes_to_dashboard, f"login Set-Cookie has all 3 security attributes: {has_secure_cookie}; redirects to /dashboard: {goes_to_dashboard}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


check(f"FastAPI login issues a secure session cookie on PORT_BASE ({PORT_BASE})", fastapi_https_smoke_test)

# --- Part 2: RAG pipeline files ---
check("rag_chunking_comparison.py exists", lambda: file_exists("rag_chunking_comparison.py"))
check("rag_chunking_comparison.py valid syntax", lambda: python_syntax_ok("rag_chunking_comparison.py"))
check("questions.yaml exists", lambda: file_exists("questions.yaml"))
check("SOURCES.md exists", lambda: file_exists("SOURCES.md"))
check("CORPUS_MANIFEST.json exists and valid", lambda: json_valid("CORPUS_MANIFEST.json"))
check("corpus/hw03 has >= 200KB of source documents", lambda: (
    sum(f.stat().st_size for f in (ROOT / "corpus/hw03").glob("*.txt")) >= 200_000,
    f"{sum(f.stat().st_size for f in (ROOT / 'corpus/hw03').glob('*.txt'))} bytes",
))
check("reports/hw03/raw/retrieval_records.json exists and valid", lambda: json_valid("reports/hw03/raw/retrieval_records.json"))
check("reports/hw03/raw/summary.json exists and valid", lambda: json_valid("reports/hw03/raw/summary.json"))
check("summary covers all 3 chunking techniques", lambda: (
    set(json.loads((ROOT / "reports/hw03/raw/summary.json").read_text()).keys()) == {"token", "semantic", "sentence_window"},
    "key check on summary.json",
))


def embedding_model_smoke_test():
    """Runs the actual pipeline's embedding call for one short query and
    checks it returns a real, correctly-shaped, non-degenerate vector --
    not the exact values (those aren't deterministic to assert on)."""
    result = subprocess.run(
        [sys.executable, "-c",
         "from llama_index.embeddings.huggingface import HuggingFaceEmbedding\n"
         "m = HuggingFaceEmbedding(model_name='sentence-transformers/all-MiniLM-L6-v2')\n"
         "v = m.get_query_embedding('test query')\n"
         "import sys; sys.exit(0 if len(v) == 384 and any(abs(x) > 1e-6 for x in v) else 1)"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    return result.returncode == 0, f"exit code {result.returncode}" + (f": {result.stderr[-200:]}" if result.returncode else "")


check("HuggingFace embedding model loads and returns a 384-dim vector", embedding_model_smoke_test)

# --- Repository-level deliverables ---
check("RUN_LOG.txt exists and non-empty", lambda: (
    (ROOT / "reports/hw03/RUN_LOG.txt").exists() and (ROOT / "reports/hw03/RUN_LOG.txt").stat().st_size > 0,
    "reports/hw03/RUN_LOG.txt",
))
check("METRICS.md exists", lambda: file_exists("reports/hw03/METRICS.md"))
check("AI_USE.md exists", lambda: file_exists("reports/hw03/AI_USE.md"))


def git_commit_hash():
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return result.returncode == 0, result.stdout.strip() or result.stderr.strip()


commit_ok, commit_hash = git_commit_hash()

passed = sum(1 for c in checks if c["passed"])
failed = len(checks) - passed

output = {
    "homework": "HW3",
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

out_path = ROOT / "reports/hw03/verification.json"
out_path.write_text(json.dumps(output, indent=2))

print(f"\n{passed}/{len(checks)} checks passed.")
print(f"Wrote {out_path}")

sys.exit(0 if failed == 0 else 1)
