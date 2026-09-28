#!/usr/bin/env python3


import json
import os
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
LOCAL_MODEL = "qwen3:8b (Ollama) + sentence-transformers/all-MiniLM-L6-v2"

DB_CONTAINER = "s8360-mysql"
DB_NAME = "s8360_rel"
DB_USER = "root"
DB_PASS = "hw4pass"

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
        return True, f"valid JSON: {path}"
    except Exception as exc:
        return False, str(exc)


def load_json(path):
    return json.loads((ROOT / path).read_text())


def mysql_query(sql: str):
    """Returns (ok, stdout_or_error). Fails gracefully if docker/container
    isn't available instead of raising, so the rest of the checks still run."""
    try:
        result = subprocess.run(
            ["docker", "exec", DB_CONTAINER, "mysql", "-N", "-u", DB_USER, f"-p{DB_PASS}", DB_NAME, "-e", sql],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, result.stdout.strip()
    except FileNotFoundError:
        return False, "docker not found on PATH"
    except subprocess.TimeoutExpired:
        return False, "docker exec timed out"


for jsx in ["Login", "Signup", "Home", "CreateRecord", "UpdateRecord", "DeleteRecord", "RequireAuth"]:
    check(f"frontend/src/components/{jsx}.jsx exists", lambda jsx=jsx: file_exists(f"frontend/src/components/{jsx}.jsx"))
check("frontend/src/api.js exists", lambda: file_exists("frontend/src/api.js"))
check("frontend/src/context/AuthContext.jsx exists", lambda: file_exists("frontend/src/context/AuthContext.jsx"))
check("frontend/src/App.jsx exists", lambda: file_exists("frontend/src/App.jsx"))


check("db.py exists", lambda: file_exists("db.py"))
check("db.py valid syntax", lambda: python_syntax_ok("db.py"))
check("db.py names the connection variable db_session_basede26 (assignment's exact requirement)", lambda: (
    "db_session_basede26" in (ROOT / "db.py").read_text(),
    "text check on db.py",
))
check("models.py exists (Course, User, Session)", lambda: file_exists("models.py"))
check("models.py valid syntax", lambda: python_syntax_ok("models.py"))
check("crud.py exists", lambda: file_exists("crud.py"))
check("crud.py valid syntax", lambda: python_syntax_ok("crud.py"))
check("api.py exists (JSON auth + course CRUD)", lambda: file_exists("api.py"))
check("api.py valid syntax", lambda: python_syntax_ok("api.py"))
check("docker-compose.yml exists (MySQL 8.0, s8360_rel)", lambda: file_exists("docker-compose.yml"))
check("scripts/init_db.py exists", lambda: file_exists("scripts/init_db.py"))
check("scripts/init_db.py valid syntax", lambda: python_syntax_ok("scripts/init_db.py"))


def db_reachable():
    ok, out = mysql_query("SELECT 1;")
    return ok, out if ok else f"MySQL not reachable via docker exec {DB_CONTAINER} -- {out}"


check("MySQL container reachable (docker exec)", db_reachable)


def tables_exist():
    ok, out = mysql_query("SHOW TABLES;")
    if not ok:
        return False, out
    tables = set(out.splitlines())
    required = {"courses", "users", "sessions", "perf_courses", "perf_course_reviews"}
    missing = required - tables
    return not missing, f"present: {sorted(tables & required)}" + (f", missing: {sorted(missing)}" if missing else "")


check("courses/users/sessions/perf_courses/perf_course_reviews tables all exist", tables_exist)

check("perf_models.py exists (PerfCourse, PerfCourseReview)", lambda: file_exists("perf_models.py"))
check("perf_models.py valid syntax", lambda: python_syntax_ok("perf_models.py"))
check("perf_api.py exists (naive + fixed endpoints)", lambda: file_exists("perf_api.py"))
check("perf_api.py valid syntax", lambda: python_syntax_ok("perf_api.py"))
check("scripts/seed_perf_data.py exists", lambda: file_exists("scripts/seed_perf_data.py"))
check("scripts/seed_perf_data.py valid syntax", lambda: python_syntax_ok("scripts/seed_perf_data.py"))
check("scripts/measure_n_plus_1.py exists", lambda: file_exists("scripts/measure_n_plus_1.py"))
check("scripts/measure_n_plus_1.py valid syntax", lambda: python_syntax_ok("scripts/measure_n_plus_1.py"))


def perf_courses_seeded():
    ok, out = mysql_query("SELECT COUNT(*) FROM perf_courses;")
    if not ok:
        return False, out
    return int(out) >= 5000, f"perf_courses has {out} rows (need >= 5000)"


def perf_reviews_seeded():
    ok, out = mysql_query("SELECT COUNT(*) FROM perf_course_reviews;")
    if not ok:
        return False, out
    return int(out) >= 200, f"perf_course_reviews has {out} rows (need >= 200)"


check("perf_courses seeded to >= 5,000 rows", perf_courses_seeded)
check("perf_course_reviews seeded to >= 200 rows", perf_reviews_seeded)
check("reports/hw04/raw/n_plus_1_records.json exists and has 180 rows (3 sizes x 2 modes x 30)", lambda: (
    len(load_json("reports/hw04/raw/n_plus_1_records.json")) == 180,
    f"{len(load_json('reports/hw04/raw/n_plus_1_records.json'))} records",
))


def n_plus_1_summary_shape_ok():
    summary = load_json("reports/hw04/raw/n_plus_1_summary.json")
    ok = True
    detail = []
    for size in (10, 50, 200):
        naive = summary.get(f"{size}_naive", {})
        fixed = summary.get(f"{size}_fixed", {})
        naive_ok = naive.get("sql_stmts_per_req") == size + 1
        fixed_ok = fixed.get("sql_stmts_per_req") == 2
        ok = ok and naive_ok and fixed_ok
        detail.append(f"{size}: naive={naive.get('sql_stmts_per_req')} fixed={fixed.get('sql_stmts_per_req')}")
    return ok, "; ".join(detail)


check("n_plus_1_summary.json: naive=page_size+1, fixed=2, for all 3 page sizes", n_plus_1_summary_shape_ok)
check("reports/hw04/raw/explain_before_after.txt exists (EXPLAIN evidence)", lambda: file_exists("reports/hw04/raw/explain_before_after.txt"))

check("rag.py exists", lambda: file_exists("rag.py"))
check("rag.py valid syntax", lambda: python_syntax_ok("rag.py"))
check("corpus/hw03 has >= 5 documents", lambda: (
    len(list((ROOT / "corpus/hw03").glob("*.txt"))) >= 5,
    f"{len(list((ROOT / 'corpus/hw03').glob('*.txt')))} .txt files",
))
check("reports/hw04/raw/rag_results.json exists with 18 records (6 questions x 3 configs)", lambda: (
    len(load_json("reports/hw04/raw/rag_results.json")) == 18,
    f"{len(load_json('reports/hw04/raw/rag_results.json'))} records",
))


def q5_q6_refused():
    records = load_json("reports/hw04/raw/rag_results.json")
    ctx_eng = [r for r in records if r["config"] == "C_context_engineered" and r["question_id"] in ("q5", "q6")]
    all_refused = all(r.get("refused_when_needed") for r in ctx_eng)
    return all_refused, f"{sum(1 for r in ctx_eng if r.get('refused_when_needed'))}/{len(ctx_eng)} refused as required"


check("Q5 and Q6 are refused under context-engineered RAG (assignment requirement)", q5_q6_refused)
check("reports/hw04/raw/k_sweep_results.json exists with k=1,3,5", lambda: (
    {r["k"] for r in load_json("reports/hw04/raw/k_sweep_results.json")} == {1, 3, 5},
    f"k values: {sorted({r['k'] for r in load_json('reports/hw04/raw/k_sweep_results.json')})}",
))
check("reports/hw04/raw/rag_evaluation_table.json exists", lambda: file_exists("reports/hw04/raw/rag_evaluation_table.json"))
check("reports/hw04/raw/rag_summary_metrics.json exists", lambda: file_exists("reports/hw04/raw/rag_summary_metrics.json"))



def backend_smoke_test():
    own_process = None
    try:
        try:
            with socket.create_connection(("127.0.0.1", PORT_BASE), timeout=0.5):
                already_up = True
        except OSError:
            already_up = False

        if not already_up:
            env = {**os.environ, "SESSION_HTTPS_ONLY": "false"}
            own_process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT_BASE)],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
            )
            deadline = time.time() + 20
            up = False
            while time.time() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", PORT_BASE), timeout=0.5):
                        up = True
                        break
                except OSError:
                    time.sleep(0.3)
            if not up:
                return False, f"server never bound to port {PORT_BASE} within 20s"

        base = f"http://127.0.0.1:{PORT_BASE}"
        curl = lambda *args: subprocess.run(["curl", "-s", *args], capture_output=True, text=True, timeout=10).stdout

        # (a) unauthenticated /api/courses -> 401
        code = curl("-o", "/dev/null", "-w", "%{http_code}", f"{base}/api/courses")
        unauth_ok = code.strip() == "401"

        # (b) login with demo creds, then /api/courses works with the cookie
        jar = "/tmp/verify_hw04_cookiejar.txt"
        curl("-c", jar, "-X", "POST", f"{base}/api/auth/login", "-H", "Content-Type: application/json",
             "-d", '{"email":"karthik.pragada@sjsu.edu","password":"data260"}')
        courses_body = curl("-b", jar, f"{base}/api/courses")
        try:
            courses_ok = isinstance(json.loads(courses_body), list) and len(json.loads(courses_body)) >= 1
        except Exception:
            courses_ok = False

        # (c) N+1 endpoint: naive uses more SQL statements than fixed, both return the same count
        naive_headers = curl("-s", "-D", "-", "-o", "/dev/null",
                              f"{base}/api/perf/courses?page=1&page_size=10&mode=naive")
        fixed_headers = curl("-s", "-D", "-", "-o", "/dev/null",
                              f"{base}/api/perf/courses?page=1&page_size=10&mode=fixed")

        def extract_count(headers):
            for line in headers.splitlines():
                if line.lower().startswith("x-sql-query-count:"):
                    return int(line.split(":")[1].strip())
            return None

        naive_n, fixed_n = extract_count(naive_headers), extract_count(fixed_headers)
        perf_ok = naive_n is not None and fixed_n is not None and naive_n > fixed_n

        detail = (
            f"unauth->401: {unauth_ok}; login+list courses ok: {courses_ok}; "
            f"naive({naive_n}) > fixed({fixed_n}) SQL stmts: {perf_ok}"
        )
        return unauth_ok and courses_ok and perf_ok, detail
    finally:
        if own_process is not None:
            own_process.terminate()
            try:
                own_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                own_process.kill()


check(f"Live backend on PORT_BASE ({PORT_BASE}): auth-gated CRUD + N+1 endpoints behave correctly", backend_smoke_test)

check("reports/hw04/RUN_LOG.txt exists and non-empty", lambda: (
    (ROOT / "reports/hw04/RUN_LOG.txt").exists() and (ROOT / "reports/hw04/RUN_LOG.txt").stat().st_size > 0,
    "reports/hw04/RUN_LOG.txt",
))
check("reports/hw04/METRICS.md exists", lambda: file_exists("reports/hw04/METRICS.md"))
check("reports/hw04/AI_USE.md exists", lambda: file_exists("reports/hw04/AI_USE.md"))


def git_commit_hash():
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return result.returncode == 0, result.stdout.strip() or result.stderr.strip()


commit_ok, commit_hash = git_commit_hash()

passed = sum(1 for c in checks if c["passed"])
failed = len(checks) - passed

output = {
    "homework": "HW4",
    "sid4": SID4,
    "commit_hash": commit_hash if commit_ok else None,
    "model": LOCAL_MODEL,
    "seed": SEED,
    "verify_seed": VERIFY_SEED,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "checks": checks,
    "passed": passed,
    "failed": failed,
    "total": len(checks),
    "overall": "PASS" if failed == 0 else "FAIL",
}

out_path = ROOT / "reports/hw04/verification.json"
out_path.write_text(json.dumps(output, indent=2))

print(f"\n{passed}/{len(checks)} checks passed.")
print(f"Wrote {out_path}")

sys.exit(0 if failed == 0 else 1)
