#!/usr/bin/env python3


import asyncio
import json
import os
import py_compile
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SID4 = 8360
PORT_BASE = 8000 + (SID4 % 900)
SEED = SID4
VERIFY_SEED = 260000 + SID4
MODEL = "qwen3:8b (Ollama) for the Part 5 agent"
RAW = ROOT / "reports/hw05/raw"

checks = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as exc:
        ok, detail = False, f"exception: {exc}"
    checks.append({"name": name, "passed": bool(ok), "detail": detail})
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name} -- {detail}", flush=True)


def exists(path):
    p = ROOT / path
    return p.exists(), f"{'found' if p.exists() else 'missing'}: {path}"


def syntax(path):
    try:
        py_compile.compile(str(ROOT / path), doraise=True)
        return True, f"valid syntax: {path}"
    except py_compile.PyCompileError as exc:
        return False, str(exc)


def jload(path):
    return json.loads((ROOT / path).read_text())


# ---- files + syntax -------------------------------------------------------------
for f in ["models.py", "schemas.py", "crud.py", "catalog_api.py", "meals_server.py", "domain_server.py", "domain_tools.py",
          "resilience.py", "execute_tool.py", "agent.py", "tests_hw5.py", "scripts/migrate_hw5.py",
          "scripts/hw5_resilience_demo.py", "scripts/hw5_agent_scenarios.py"]:
    check(f"{f} exists and has valid Python syntax", lambda f=f: (exists(f)[0] and syntax(f)[0], syntax(f)[1] if exists(f)[0] else f"missing: {f}"))
for f in ["frontend/src/store/index.js", "frontend/src/store/coursesSlice.js", "frontend/src/store/client.js"]:
    check(f"{f} exists", lambda f=f: exists(f))
check("coursesSlice defines the four thunks (fetch/create/update/delete)", lambda: (
    all(t in (ROOT / "frontend/src/store/coursesSlice.js").read_text() for t in ("fetchCourses", "createCourse", "updateCourse", "deleteCourse")),
    "text check on coursesSlice.js"))


# ---- Part 1: live backend ------------------------------------------------------------
def backend():
    own = None
    try:
        try:
            socket.create_connection(("127.0.0.1", PORT_BASE), timeout=0.5).close()
        except OSError:
            own = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT_BASE)],
                                   cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, "SESSION_HTTPS_ONLY": "false"})
            for _ in range(60):
                try:
                    socket.create_connection(("127.0.0.1", PORT_BASE), timeout=0.5).close()
                    break
                except OSError:
                    time.sleep(0.3)
            else:
                return False, f"backend never bound to {PORT_BASE}"
        import requests
        base = f"http://127.0.0.1:{PORT_BASE}/api"
        anon = requests.get(f"{base}/instructors").status_code
        s = requests.Session()
        login = s.post(f"{base}/auth/login", json={"email": "karthik.pragada@sjsu.edu", "password": "data260"}).status_code
        inst = s.get(f"{base}/instructors?page=1&page_size=2")
        page = inst.json() if inst.ok else {}
        first = page.get("items", [{}])[0].get("id")
        rel = s.get(f"{base}/instructors/{first}/courses") if first else None
        bad_email = s.post(f"{base}/instructors", json={"name": "x", "department": "", "email": "nope"}).status_code
        bad_code = s.post(f"{base}/courses", json={"courseTitle": "x", "courseCode": "bad code", "seatsAvailable": 1, "instructorId": first or 1}).status_code
        missing = s.get(f"{base}/courses/999999").status_code
        blocked = s.delete(f"{base}/instructors/{first}").status_code if rel is not None and rel.ok and rel.json() else None
        ok = (anon == 401 and login == 200 and inst.ok and "total" in page and rel is not None and rel.ok and rel.json()
              and bad_email == 422 and bad_code == 422 and missing == 404 and blocked == 409)
        return ok, (f"unauth={anon} login={login} paged-list ok={inst.ok} relationship rows={len(rel.json()) if rel is not None and rel.ok else None} "
                    f"bad-email={bad_email} bad-code={bad_code} missing={missing} delete-with-courses={blocked}")
    finally:
        if own:
            own.terminate()
            try:
                own.wait(timeout=5)
            except subprocess.TimeoutExpired:
                own.kill()


check(f"FastAPI on PORT_BASE ({PORT_BASE}): auth, paginated list, relationship query, 404/422/409 behaviour", backend)


# ---- Part 2: both MCP servers over real STDIO -------------------------------------------
async def _mcp(server, tool, args):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / server)], cwd=str(ROOT))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            res = await session.call_tool(tool, args)
            text = "".join(c.text for c in res.content if getattr(c, "type", "") == "text")
            return tools, bool(res.isError), text


def meals_server():
    tools, is_err, text = asyncio.run(_mcp("meals_server.py", "search_meals_by_name", {"query": "x", "limit": 99}))
    ok = set(tools) == {"search_meals_by_name", "meals_by_ingredient", "random_meal", "meal_details"} and is_err
    return ok, f"4 tools listed: {sorted(tools)}; out-of-range limit rejected with a tool error: {is_err}"


def domain_server():
    tools, is_err, text = asyncio.run(_mcp("domain_server.py", "course_stats", {"group_by": "department"}))
    env = json.loads(text)
    ok = len(tools) == 3 and not is_err and env["ok"] is True and env["error"] is None
    return ok, f"3 tools listed: {sorted(tools)}; course_stats envelope ok={env['ok']}, error={env['error']}"


check("meals MCP server starts over STDIO, lists 4 tools, answers a tool call", meals_server)
check("domain MCP server starts over STDIO, lists 3 tools, returns {ok,data,error}", domain_server)

# ---- Parts 3-5: artifacts + offline tests ---------------------------------------------------
check("reports/hw05/raw/fault_injection_calls.json has 150 records (3 rates x 50)", lambda: (
    len(jload("reports/hw05/raw/fault_injection_calls.json")) == 150, f"{len(jload('reports/hw05/raw/fault_injection_calls.json'))} records"))
check("fault-injection summary covers 0%/20%/50% and was reproducible under VERIFY_SEED", lambda: (
    [r["injected_failure_rate"] for r in jload("reports/hw05/raw/fault_injection_summary.json")["rows"]] == ["0%", "20%", "50%"]
    and jload("reports/hw05/raw/fault_injection_summary.json")["reproducible"] is True
    and jload("reports/hw05/raw/fault_injection_summary.json")["verify_seed"] == VERIFY_SEED,
    f"verify_seed={jload('reports/hw05/raw/fault_injection_summary.json')['verify_seed']}"))


def fault_seed_replay():
    """Re-derive the failure sequence from VERIFY_SEED alone and compare it to the saved raw data."""
    import random
    calls = jload("reports/hw05/raw/fault_injection_calls.json")
    for rate in (0.2, 0.5):
        rng = random.Random(VERIFY_SEED)
        expected_faults = 0
        for c in [x for x in calls if x["failure_rate"] == rate]:
            for _ in range(c["attempts"]):
                if rng.random() < rate:
                    expected_faults += 1
        saved = sum(c["attempts"] - (1 if c["ok"] else 0) for c in calls if c["failure_rate"] == rate)
        if expected_faults != saved:
            return False, f"rate {rate}: seed replay gives {expected_faults} faults, raw data has {saved}"
    return True, "seed replay reproduces the saved failure counts at 20% and 50%"


check("VERIFY_SEED replay matches the saved raw failure sequence", fault_seed_replay)


def agent_log():
    rows = [json.loads(l) for l in (ROOT / "reports/hw05/raw/agent_runs.jsonl").read_text().splitlines()]
    stops = {r["stop_reason"] for r in rows if r["event"] == "stop"}
    runs = {r["run_id"] for r in rows}
    return len(runs) >= 4 and stops >= {"final_answer", "safety_block", "max_steps"}, f"{len(runs)} runs; stop reasons seen: {sorted(stops)}"


check("agent_runs.jsonl: >= 4 runs and all three stop reasons logged", agent_log)


def offline_tests():
    r = subprocess.run([sys.executable, "tests_hw5.py"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    last = [l for l in r.stdout.splitlines() if "tests passed" in l]
    return r.returncode == 0 and bool(last), last[-1] if last else r.stdout[-200:]


check("offline test runner (no DB / network / LLM) passes", offline_tests)
for f in ["reports/hw05/RUN_LOG.txt", "reports/hw05/METRICS.md", "reports/hw05/AI_USE.md", "reports/hw05/REFLECTION.md", "reports/hw05/Pragada_HW5.pdf"]:
    check(f"{f} exists and is non-empty", lambda f=f: ((ROOT / f).exists() and (ROOT / f).stat().st_size > 0, f))

commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or None
passed = sum(c["passed"] for c in checks)
out = {"homework": "HW5", "sid4": SID4, "commit_hash": commit, "model": MODEL, "seed": SEED, "verify_seed": VERIFY_SEED,
       "timestamp": datetime.now(timezone.utc).isoformat(), "checks": checks, "passed": passed,
       "failed": len(checks) - passed, "total": len(checks), "overall": "PASS" if passed == len(checks) else "FAIL"}
(ROOT / "reports/hw05/verification.json").write_text(json.dumps(out, indent=2))
print(f"\n{passed}/{len(checks)} checks passed.\nWrote reports/hw05/verification.json")
sys.exit(0 if passed == len(checks) else 1)
