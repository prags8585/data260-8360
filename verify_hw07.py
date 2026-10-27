#!/usr/bin/env python3

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SID4 = 8360
PORT_BASE = 8000 + (SID4 % 900)
SEED = SID4
VERIFY_SEED = 260000 + SID4
MODEL = "qwen3:8b (Ollama); verification agent run at temperature 0, seed VERIFY_SEED"
RAW = ROOT / "reports/hw07/raw"
checks = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as exc:  # a failing check must not stop the others
        ok, detail = False, f"exception: {type(exc).__name__}: {exc}"
    checks.append({"name": name, "passed": bool(ok), "detail": detail})
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name} -- {detail}", flush=True)


def jload(path):
    return json.loads((ROOT / path).read_text())


def with_backend(fn):
    own = None
    try:
        try:
            socket.create_connection(("127.0.0.1", PORT_BASE), timeout=0.5).close()
        except OSError:
            own = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(PORT_BASE)], cwd=ROOT,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, "SESSION_HTTPS_ONLY": "false"})
            for _ in range(120):
                try:
                    socket.create_connection(("127.0.0.1", PORT_BASE), timeout=0.5).close()
                    break
                except OSError:
                    time.sleep(0.5)
            else:
                return False, f"backend never bound to {PORT_BASE}"
        return fn(f"http://127.0.0.1:{PORT_BASE}")
    finally:
        if own:
            own.terminate()
            own.wait(timeout=10)


# ---- Part 1: JWT + roles ---------------------------------------------------------------------------------
def jwt_roles(base):
    import requests

    def login(user, password):
        return requests.post(f"{base}/auth/login", json={"username": user, "password": password}, timeout=15)

    good, bad = login("writer1", "Writer#Pass2026"), login("writer1", "wrong")
    tokens = {u: login(u, p).json().get("access_token") for u, p in
              (("reader1", "Reader#Pass2026"), ("writer1", "Writer#Pass2026"), ("moderator1", "Moderator#Pass2026"))}
    auth = lambda u: {"Authorization": f"Bearer {tokens[u]}"}  # noqa: E731
    course = {"courseTitle": "Verify HW7", "courseCode": "VER-707", "seatsAvailable": 5, "instructorId": 1}
    no_token = requests.get(f"{base}/auth/me", timeout=15).status_code
    bad_token = requests.get(f"{base}/auth/me", headers={"Authorization": "Bearer abc.def.ghi"}, timeout=15).status_code
    me = requests.get(f"{base}/auth/me", headers=auth("writer1"), timeout=15).json()
    reader_create = requests.post(f"{base}/api/courses", json=course, headers=auth("reader1"), timeout=15).status_code
    created = requests.post(f"{base}/api/courses", json=course, headers=auth("writer1"), timeout=15)
    cid = created.json().get("id")
    try:
        writer_delete = requests.delete(f"{base}/api/courses/{cid}", headers=auth("writer1"), timeout=15).status_code
        listed = requests.get(f"{base}/api/courses", headers=auth("reader1"), timeout=15).status_code
    finally:
        mod_delete = requests.delete(f"{base}/api/courses/{cid}", headers=auth("moderator1"), timeout=15).status_code
    ok = (good.status_code == 200 and "access_token" in good.json() and bad.status_code == 401 and no_token == 401 and bad_token == 401
          and me.get("role") == "writer" and reader_create == 403 and created.status_code == 201 and writer_delete == 403
          and mod_delete == 204 and listed == 200)
    return ok, (f"login={good.status_code}/bad-login={bad.status_code} me(no token)={no_token} me(bad token)={bad_token} reader-create={reader_create} "
                f"writer-create={created.status_code} writer-delete={writer_delete} moderator-delete={mod_delete} list={listed}")


def users_table():
    from sqlalchemy import text

    from db import engine
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT username, role, password_hash FROM users")).fetchall()
    roles = {r[1] for r in rows}
    hashed = all(str(r[2]).startswith("$2") for r in rows)
    return {"reader", "writer", "moderator"} <= roles and hashed, f"{len(rows)} users, roles {sorted(roles)}, every password_hash is a bcrypt hash: {hashed}"


# ---- Part 2: the agent loop ------------------------------------------------------------------------------
def agent_task():
    from hw7_cases import CASES_BY_ID
    from src.model_client import ModelClient
    from tool_agent import run_agent
    case = CASES_BY_ID["A"]
    result = run_agent(case.prompt, model=ModelClient("qwen3:8b", 0.0, num_predict=400, seed=VERIFY_SEED), min_tool_calls=case.min_tool_calls,
                       required_tools=case.required_tools)
    verdict = case.verifier(result)
    return result["stop_reason"] == "final_answer" and result["total_tool_calls"] >= 2 and verdict.passed, \
        f"stop={result['stop_reason']} tool_calls={result['total_tool_calls']} verifier={'pass' if verdict.passed else verdict.assertion}"


def error_recovery():
    from src.model_client import ModelClient
    from tool_agent import run_agent
    result = run_agent("Show me the full details of the course with id 99999.", model=ModelClient("qwen3:8b", 0.0, num_predict=300, seed=VERIFY_SEED))
    first = result["tool_calls"][0] if result["tool_calls"] else {}
    return result["stop_reason"] == "final_answer" and first.get("ok") is False and "not found" in first.get("observation", ""), \
        f"stop={result['stop_reason']} first tool ok={first.get('ok')}"


def reliability_data():
    s = jload("reports/hw07/raw/reliability_summary.json")["summary"]
    return s["attempts"] >= 20 and s["rate_after_repair"] >= s["rate_before_repair"], \
        f"{s['attempts']} attempts, well-formed {s['rate_before_repair']:.1%} -> {s['rate_after_repair']:.1%}, failures {s['failures_by_type']}"


# ---- Part 3 ----------------------------------------------------------------------------------------------
def reflexion_data():
    d = jload("reports/hw07/raw/reflexion_comparison.json")["summary"]
    stored = [json.loads(ln) for ln in (RAW / "reflections.jsonl").read_text().splitlines() if ln.strip()]
    reasons = set(d["reflexion"]["stop_reasons"])
    return bool(stored) and reasons <= {"success", "budget_exhausted", "human_review"} and all("evidence" in r and "reflection" in r for r in stored), \
        f"{len(stored)} stored reflections with evidence; stop reasons {sorted(reasons)}"


def reflexion_bounds():
    from dataclasses import replace

    from hw7_cases import CASES_BY_ID, Check
    from reflexion import ReflectionStore, run_with_reflexion
    from src.model_client import CompletionResult
    from tool_agent import Tool, Toolbox

    class Stub:
        def complete(self, messages, tools=None):
            return CompletionResult("an answer", 1, 1, 2)

    case = replace(CASES_BY_ID["A"], verifier=lambda _r: Check(False, "x", "y"), min_tool_calls=0, required_tools={})
    with tempfile.TemporaryDirectory() as d:
        out = run_with_reflexion(case, lambda a: Stub(), run_id="v", store=ReflectionStore(Path(d) / "r.jsonl"), toolbox=Toolbox([Tool("t", "t", {"type": "object"}, lambda a: "{}")]))
    return out["retries"] == 2 and out["stop_reason"] == "human_review", f"retries={out['retries']} stop={out['stop_reason']} (never more than 2 retries)"


# ---- Part 4 / 5 -------------------------------------------------------------------------------------------
def tools_contract():
    from bikeshare import tools as bt
    store = bt.TripStore((RAW / "scenarios/scenario_A_membership_wins.csv").read_text())
    calc_ok, calc_bad = bt.calculator("(29*4)/2"), bt.calculator("__import__('os')")
    select = bt.csv_sql(store, "SELECT COUNT(*) AS n FROM trips")
    drop = bt.csv_sql(store, "DROP TABLE trips")
    envelopes = all({"success", "ts"} <= set(e) for e in (calc_ok, calc_bad, select, drop))
    return (envelopes and calc_ok["data"]["value"] == 58.0 and not calc_bad["success"] and select["success"] and select["data"]["row_count"] == 1
            and not drop["success"] and store.row_count >= 500), f"calculator whitelist ok, csv_sql SELECT ok / DROP rejected, {store.row_count} rows loaded"


def scenarios_and_snapshots():
    c = jload("reports/hw07/raw/scenarios/scenario_construction.json")["scenarios"]
    a, b = c["scenario_A_membership_wins.csv"], c["scenario_B_pay_per_use_wins.csv"]
    snaps = sorted((RAW / "snapshots").glob("*_pricing_snapshot.json"))
    meta = [json.loads(p.read_text()) for p in snaps]
    return (a["summary"]["rows"] >= 500 and b["summary"]["rows"] >= 500 and a["reference_costs"]["decision"] != b["reference_costs"]["decision"]
            and len(meta) >= 2 and all(len(m["sha256"]) == 64 and m["accessed_at"] and m["url"] for m in meta)), \
        f"A: {a['summary']['rows']} rows -> {a['reference_costs']['decision']}; B: {b['summary']['rows']} rows -> {b['reference_costs']['decision']}; {len(meta)} pricing snapshots with SHA-256"


def attack_data():
    d = jload("reports/hw07/raw/attack_results.json")
    cells = {(r["config"], r["attack"], r["condition"]) for r in d["runs"] if r["attack"] != "control_clean"}
    fixtures = [p for p in (ROOT / "fixtures/hw07").glob("hostile_*.html")]
    return len(cells) == 9 * len(d["configs"]) and len(fixtures) == 3, \
        f"{len(d['runs'])} attack runs over {len(cells)} config/attack/condition cells ({', '.join(d['configs'])}); {len(fixtures)} hostile fixtures"


def readonly_contract_blocks_mutation():
    from bikeshare import tools as bt
    store = bt.TripStore((RAW / "scenarios/scenario_B_pay_per_use_wins.csv").read_text())
    attempts = ["DELETE FROM trips", "DROP TABLE trips", "SELECT 1; DELETE FROM trips", "UPDATE trips SET duration_min = 0"]
    rejected = all(not bt.csv_sql(store, a)["success"] for a in attempts)
    n = bt.csv_sql(store, "SELECT COUNT(*) AS n FROM trips")["data"]["rows"][0]["n"]
    return rejected and n == store.row_count and not store.mutated, f"{len(attempts)} mutation attempts rejected; table still has {n} rows"


# ---- Part 6 -----------------------------------------------------------------------------------------------
def safety_gate():
    import file_tools as ft
    passes = ["ls -la", "cat notes.txt", "grep -n DEBUG app.py", "git status", "echo hello world"]
    blocks = ["rm -fr /tmp/build", "sudo ls /root", "chmod 777 notes.txt", "cat /dev/zero > /dev/sda", "sort -o /etc/hosts notes.txt"]
    ok = all(ft.confirm_bash(c)["allowed"] for c in passes) and not any(ft.confirm_bash(c)["allowed"] for c in blocks)
    safe_prefix_but_destructive = ft.is_destructive("ls") is False and ft.confirm_bash("sudo ls", auto_approve=True)["allowed"]
    return ok and safe_prefix_but_destructive, "5 safe commands allowed, 5 destructive commands blocked (including ones that start with an allow-listed command)"


def file_tool_integration():
    import file_tools as ft
    with tempfile.TemporaryDirectory() as d:
        ft.write_file("a.py", "x = 1\n", root=d)
        ft.write_file("b.py", "DEBUG = True\n", root=d)
        ft.write_file("c.py", "y = 2\n", root=d)
        files = ft.glob_files("*.py", root=d)["files"]
        hits = ft.search_in_files("DEBUG", "*.py", root=d)["matches"]
        content = ft.read_file(hits[0]["file"], root=d)["content"]
    return files == ["a.py", "b.py", "c.py"] and hits[0]["file"] == "b.py" and "DEBUG = True" in content, "glob -> search -> read finds b.py containing DEBUG"


def gate_results_file():
    d = jload("reports/hw07/raw/safety_gate_results_final.json")
    return d["correct"] == 10 and not d["false_allows"], f"{d['correct']}/10 correct, false allows: {d['false_allows'] or 'none'}"


# ---- repo hygiene -----------------------------------------------------------------------------------------
def offline_tests():
    r = subprocess.run([sys.executable, "tests_hw7.py"], cwd=ROOT, capture_output=True, text=True, timeout=300)
    last = [ln for ln in r.stdout.splitlines() if "tests passed" in ln]
    return r.returncode == 0 and bool(last), last[-1] if last else r.stdout[-200:]


def ruff_clean():
    r = subprocess.run([str(ROOT / ".venv/bin/ruff"), "check", "."], cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0 and (ROOT / ".pre-commit-config.yaml").exists(), (r.stdout.strip().splitlines() or ["ruff: no output"])[-1]


for name, fn in [
    ("JWT: login/401, /auth/me 401, role policy 403/201/204, list 200 on the live API", lambda: with_backend(jwt_roles)),
    ("MySQL users table: roles reader/writer/moderator and bcrypt password hashes", users_table),
    ("agent loop completes a multi-step verification task (>= 2 tool calls, verifier passes)", agent_task),
    ("agent loop handles a nonexistent id without crashing", error_recovery),
    ("20+ attempt reliability results saved (well-formed rate before/after repair)", reliability_data),
    ("Reflexion comparison data and stored reflections with evidence", reflexion_data),
    ("Reflexion is bounded: at most 2 retries, clean stop reason", reflexion_bounds),
    ("csv_sql / calculator / policy tools: common envelope, whitelist, read-only contract", tools_contract),
    ("two 500+ row scenarios with different decisions and SHA-256 pricing snapshots", scenarios_and_snapshots),
    ("prompt-injection before/after data for 3 attacks x 3 conditions and 3 hostile fixtures", attack_data),
    ("read-only SELECT contract rejects mutation attempts at the tool boundary", readonly_contract_blocks_mutation),
    ("safety gate: 5 safe commands pass, 5 destructive commands blocked", safety_gate),
    ("file tools: glob -> search -> read finds the file containing DEBUG", file_tool_integration),
    ("saved 10-command gate run: 10/10 correct and no false allow", gate_results_file),
    ("offline test suite passes (no DB / network / model)", offline_tests),
    ("ruff passes on the repository and pre-commit config exists", ruff_clean),
]:
    check(name, fn)
for f in ["reports/hw07/RUN_LOG.txt", "reports/hw07/METRICS.md", "reports/hw07/AI_USE.md", "reports/hw07/Pragada_HW7.pdf"]:
    check(f"{f} exists and is non-empty", lambda f=f: ((ROOT / f).exists() and (ROOT / f).stat().st_size > 0, f))

commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or None
passed = sum(c["passed"] for c in checks)
out = {"homework": "HW7", "sid4": SID4, "commit_hash": commit, "model": MODEL, "seed": SEED, "verify_seed": VERIFY_SEED,
       "timestamp": datetime.now(timezone.utc).isoformat(), "checks": checks, "passed": passed, "failed": len(checks) - passed,
       "total": len(checks), "overall": "PASS" if passed == len(checks) else "FAIL"}
(ROOT / "reports/hw07/verification.json").write_text(json.dumps(out, indent=2))
print(f"\n{passed}/{len(checks)} checks passed.\nWrote reports/hw07/verification.json")
sys.exit(0 if passed == len(checks) else 1)
