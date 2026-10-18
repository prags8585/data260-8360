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
sys.path.insert(0, str(ROOT))

SID4 = 8360
PORT_BASE = 8000 + (SID4 % 900)
SEED = SID4
VERIFY_SEED = 260000 + SID4
MODEL = "qwen3:8b (Ollama), temperature 0"
RAW = ROOT / "reports/hw06/raw"
VERIFY_USER = f"verify-hw06-{VERIFY_SEED}"

checks = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as exc:  # a failing check must not stop the others
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


# ---- files + syntax ------------------------------------------------------------------
for f in ["docdb/config.py", "docdb/mongo.py", "docdb/schemas.py", "docdb/routes.py", "docdb/server.py",
          "agent_memory/service.py", "agent_memory/routes.py", "agent_memory/store.py", "agent_memory/episodes.py",
          "agent_memory/summaries.py", "agent_memory/policies.py", "agent_memory/prompt.py", "agent_memory/usage_log.py",
          "file_memory.py", "file_memory_agent.py", "tests_hw6.py", "scripts/check_agent_md.py",
          "scripts/hw6_memory_experiment.py", "scripts/hw6_cost_estimate.py"]:
    check(f"{f} exists and has valid Python syntax",
          lambda f=f: (exists(f)[0] and syntax(f)[0], syntax(f)[1] if exists(f)[0] else f"missing: {f}"))


# ---- live backend: Parts 1 and 2 -------------------------------------------------------
def with_backend(fn):
    own = None
    try:
        try:
            socket.create_connection(("127.0.0.1", PORT_BASE), timeout=0.5).close()
        except OSError:
            own = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT_BASE)],
                                   cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(100):
                try:
                    socket.create_connection(("127.0.0.1", PORT_BASE), timeout=0.5).close()
                    break
                except OSError:
                    time.sleep(0.3)
            else:
                return False, f"backend never bound to {PORT_BASE}"
        return fn(f"http://127.0.0.1:{PORT_BASE}")
    finally:
        if own:
            own.terminate()
            try:
                own.wait(timeout=5)
            except subprocess.TimeoutExpired:
                own.kill()


def part1_api(base):
    import requests
    url = f"{base}/api/course-docs"
    good = {"title": "Verify HW6 course", "category": "Data Science", "start_date": "2027-03-01T09:00:00Z"}
    created = requests.post(url, json=good, timeout=15)
    doc = created.json() if created.status_code == 201 else {}
    statuses = {
        "create": created.status_code,
        "default_status": doc.get("status"),
        "get": requests.get(f"{url}/{doc.get('id')}", timeout=15).status_code if doc else None,
        "update": requests.put(f"{url}/{doc.get('id')}", json={**good, "status": "closed"}, timeout=15).status_code if doc else None,
        "missing_title": requests.post(url, json={k: v for k, v in good.items() if k != "title"}, timeout=15).status_code,
        "bad_enum": requests.post(url, json={**good, "category": "Art"}, timeout=15).status_code,
        "wrong_type": requests.post(url, json={**good, "title": 123}, timeout=15).status_code,
        "not_found": requests.get(f"{url}/6acddcfa5623c47602c60000", timeout=15).status_code,
        "delete": requests.delete(f"{url}/{doc.get('id')}", timeout=15).status_code if doc else None,
    }
    ok = (statuses["create"] == 201 and statuses["default_status"] == "open" and statuses["get"] == 200
          and statuses["update"] == 200 and statuses["missing_title"] == 422 and statuses["bad_enum"] == 422
          and statuses["wrong_type"] == 422 and statuses["not_found"] == 404 and statuses["delete"] == 204)
    return ok, str(statuses)


def _drop_usage_rows(user_id):
    """Remove this script's own rows from the experiment's usage log again."""
    import csv
    log = RAW / "chat_usage_log.csv"
    with log.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, [r for r in reader if r["user_id"] != user_id]
    with log.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def part2_api(base):
    import requests
    from docdb.mongo import get_db
    try:
        r = requests.post(f"{base}/api/chat", timeout=180, json={
            "user_id": VERIFY_USER, "session_id": "verify", "message": "Hi, my name is Verify Bot and I like databases."})
        body = r.json() if r.ok else {}
        mem = requests.get(f"{base}/api/memory/{VERIFY_USER}", timeout=30)
        agg = requests.get(f"{base}/api/aggregate/{VERIFY_USER}", timeout=30)
        usage = body.get("usage", {})
        ok = (r.status_code == 200 and bool(body.get("reply")) and usage.get("prompt_tokens", 0) > 0
              and {"system_primer", "long_term_summary", "short_term_window", "episodic_facts", "current_message"} <= set(usage.get("components", {}))
              and mem.status_code == 200 and agg.status_code == 200
              and agg.json().get("total_messages") == 2)
        return ok, (f"chat={r.status_code} reply_chars={len(body.get('reply', ''))} prompt_tokens={usage.get('prompt_tokens')} "
                    f"components={sorted(usage.get('components', {}))} memory={mem.status_code} aggregate={agg.status_code}")
    finally:
        db = get_db()
        for coll in ("messages", "summaries", "episodes"):
            db[coll].delete_many({"user_id": VERIFY_USER})
        _drop_usage_rows(VERIFY_USER)


check(f"Part 1: course-document CRUD + validation errors on PORT_BASE {PORT_BASE}", lambda: with_backend(part1_api))
check("Part 2: POST /api/chat + GET /api/memory + GET /api/aggregate with component token counts", lambda: with_backend(part2_api))


def mongo_validators():
    from docdb.mongo import get_db
    db = get_db()
    names = set(db.list_collection_names())
    need = {"course_documents", "messages", "summaries", "episodes"}
    info = db.command("listCollections", filter={"name": "course_documents"})["cursor"]["firstBatch"][0]
    has_validator = "$jsonSchema" in info.get("options", {}).get("validator", {})
    try:
        db.course_documents.insert_one({"title": "x", "status": "archived", "category": "Art"})
        rejected = False
    except Exception as exc:
        rejected = "validation" in str(exc).lower()
    return need <= names and has_validator and rejected, f"collections={sorted(names)}, $jsonSchema validator={has_validator}, invalid insert rejected by MongoDB={rejected}"


check("MongoDB s8360_doc has the four collections and the validator rejects an invalid insert", mongo_validators)


# ---- Part 3: probes, sweep, cost ---------------------------------------------------------
def probes():
    import yaml
    y = yaml.safe_load((ROOT / "memory_probes.yaml").read_text())
    n = len(y["probes"])
    return n == 5 and "rubric" in y, f"{n} probes, rubric keys={sorted(y['rubric'])}"


def sweep():
    s = jload("reports/hw06/raw/memory_settings_summary.json")
    rows = s["rows"] if isinstance(s, dict) and "rows" in s else s
    tags = [r.get("setting") or r.get("tag") for r in rows]
    need = {"N4", "N12", "N30", "compress_N12"}
    csv_rows = sum(1 for _ in (RAW / "short_term_sweep_turns.csv").open()) - 1
    return need <= set(tags) and csv_rows >= 4 * 30, f"settings={tags}, per-turn rows in csv={csv_rows}"


def cost():
    c = jload("reports/hw06/raw/memory_cost_table.json")
    rows = c["rows"]
    return len(rows) >= 4 and bool(c["best"]) and bool(c["worst"]), f"{len(rows)} settings, best={c['best']}, worst={c['worst']}"


check("memory_probes.yaml has 5 probes and a 1-5 rubric", probes)
check("short-term sweep covers N=4/12/30 + compression with 30 turns each (raw per-turn data)", sweep)
check("cost table (10,000 x 30 turns) identifies best and worst settings", cost)


# ---- Part 4: file memory -------------------------------------------------------------------
def consolidation():
    import file_memory as fm
    original = (RAW / "memory_consolidation/MEMORY.original.md").read_text()
    new, report = fm.consolidate(original, datetime.now(timezone.utc))
    again, _ = fm.consolidate(new, datetime.now(timezone.utc))
    idem = fm.count_memory_lines(new) == fm.count_memory_lines(again)
    ok = (len(original.splitlines()) == 55 and len(new.splitlines()) < 40 and report.duplicates_merged >= 3
          and len(report.contradictions) >= 3 and idem)
    return ok, (f"{len(original.splitlines())} -> {len(new.splitlines())} lines; {report.duplicates_merged} duplicates merged, "
                f"{len(report.contradictions)} contradictions resolved; idempotent={idem}")


def agent_md():
    import re
    text = (ROOT / "AGENT.md").read_text()
    instr = re.findall(r"^\d+\.\s", text, flags=re.M)
    heads = [h for h in re.findall(r"^## (.+)$", text, flags=re.M)]
    return len(instr) >= 5 and len(heads) >= 3, f"{len(instr)} numbered instructions under {len(heads)} headings"


def checker():
    r = subprocess.run([sys.executable, "scripts/check_agent_md.py"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    last = [l for l in r.stdout.splitlines() if "AGENT.md checks passed" in l]
    return r.returncode == 0 and bool(last), last[-1] if last else r.stdout[-200:]


def offline_tests():
    r = subprocess.run([sys.executable, "tests_hw6.py"], cwd=ROOT, capture_output=True, text=True, timeout=180)
    last = [l for l in r.stdout.splitlines() if "tests passed" in l]
    return r.returncode == 0 and bool(last), last[-1] if last else r.stdout[-200:]


check("55-line MEMORY.md consolidates to < 40 lines (>= 3 duplicates, >= 3 contradictions, idempotent)", consolidation)
check("AGENT.md has >= 5 instructions across >= 3 categories", agent_md)
check("function written under AGENT.md passes the compliance checker", checker)
check("offline test runner (no DB / network / LLM) passes", offline_tests)

for f in ["reports/hw06/RUN_LOG.txt", "reports/hw06/METRICS.md", "reports/hw06/AI_USE.md", "reports/hw06/Pragada_HW6.pdf",
          "reports/hw06/raw/memory_consolidation/MEMORY.consolidated.md", "reports/hw06/raw/memory_probes_scoring.json",
          "reports/hw06/raw/chat_usage_log.csv"]:
    check(f"{f} exists and is non-empty", lambda f=f: ((ROOT / f).exists() and (ROOT / f).stat().st_size > 0, f))

commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or None
passed = sum(c["passed"] for c in checks)
out = {"homework": "HW6", "sid4": SID4, "commit_hash": commit, "model": MODEL, "seed": SEED, "verify_seed": VERIFY_SEED,
       "timestamp": datetime.now(timezone.utc).isoformat(), "checks": checks, "passed": passed,
       "failed": len(checks) - passed, "total": len(checks), "overall": "PASS" if passed == len(checks) else "FAIL"}
(ROOT / "reports/hw06/verification.json").write_text(json.dumps(out, indent=2))
print(f"\n{passed}/{len(checks)} checks passed.\nWrote reports/hw06/verification.json")
sys.exit(0 if passed == len(checks) else 1)
