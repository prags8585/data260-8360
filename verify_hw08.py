#!/usr/bin/env python3

import json
import re
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from kafka_svc import config  # noqa: E402
from kafka_svc.probe import end_offsets, seed_group  # noqa: E402
from kafka_svc.rpc import KafkaRpcClient  # noqa: E402

SID4 = int(config.SID4)
MODEL = "Part 1/3: no model. Part 2 agents: qwen3:8b via Ollama (temperature 0, seed SEED); the live check below uses the rule brain"
RAW = ROOT / "reports/hw08/raw"
COURSE = {"courseTitle": "Verify HW8", "courseCode": "VER-808", "seatsAvailable": 7, "instructorId": 1}
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


# ---- Part 1: request/response over Kafka -----------------------------------------------------------------
def containers_running():
    out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True).stdout.split()
    needed = ["s8360-kafka", "s8360-worker", "s8360-api"]
    return all(n in out for n in needed), f"running: {[n for n in needed if n in out]}"


def topics_exist():
    out = subprocess.run(["docker", "exec", "s8360-kafka", "/opt/kafka/bin/kafka-topics.sh", "--bootstrap-server", "localhost:9092", "--describe"],
                         capture_output=True, text=True).stdout
    found = {name: int(count) for name, count in re.findall(r"Topic: (\S+)\s+TopicId: \S+\s+PartitionCount: (\d+)", out)}
    ok = all(found.get(t) == n for t, n in config.TOPIC_PARTITIONS.items())
    return ok, f"{len(found)} topics, partitions {dict(sorted((t, n) for t, n in found.items() if t in config.TOPIC_PARTITIONS))}"


def kafka_round_trip():
    client = KafkaRpcClient("verify-hw08").start()
    try:
        cid = str(uuid.uuid4())
        created = client.call("CREATE_COURSE", COURSE, cid)
        fetched = client.call("GET_COURSE", {"course_id": created.get("course_id")}, cid)
        missing = client.call("GET_COURSE", {"course_id": "nope"}, "verify-missing")
        unknown = client.call("DELETE_COURSE", {}, "verify-unknown")
        invalid = client.call("CREATE_COURSE", {**COURSE, "courseTitle": ""}, "verify-invalid")
    finally:
        client.close()
    ok = (created.get("success") and len(created.get("course_id", "")) == 36 and created["correlation_id"] == cid
          and fetched.get("success") and fetched["course"]["course_id"] == created["course_id"] and fetched["course"]["courseCode"] == "VER-808"
          and fetched["correlation_id"] == cid
          and missing == {"correlation_id": "verify-missing", "success": False, "error": "Course not found"}
          and unknown["success"] is False and unknown["error"] == "Unknown operation" and unknown["correlation_id"] == "verify-unknown"
          and invalid["success"] is False and invalid["correlation_id"] == "verify-invalid")
    return ok, f"CREATE->GET round trip keeps correlation_id; unknown id -> '{missing.get('error')}'; unknown op -> '{unknown.get('error')}'; invalid -> '{invalid.get('error')}'"


def api_round_trip():
    import httpx
    base = f"http://127.0.0.1:{config.PORT_BASE}"
    cid = str(uuid.uuid4())
    created = httpx.post(f"{base}/courses", json=COURSE, headers={"X-Correlation-ID": cid}, timeout=15)
    fetched = httpx.get(f"{base}/courses/{created.json().get('course_id')}", headers={"X-Correlation-ID": cid}, timeout=15)
    missing = httpx.get(f"{base}/courses/nope", timeout=15)
    ok = (created.status_code == 201 and created.json()["correlation_id"] == cid and created.headers["x-correlation-id"] == cid
          and fetched.status_code == 200 and fetched.json()["course"]["courseTitle"] == "Verify HW8" and missing.status_code == 404)
    return ok, f"POST /courses={created.status_code} GET /courses/<id>={fetched.status_code} unknown id={missing.status_code}, X-Correlation-ID echoed"


# ---- Part 2: three agents ---------------------------------------------------------------------------------
def pipeline():
    run = uuid.uuid4().hex[:6]
    groups = {"planner": f"verify_planner_{run}", "writer": f"verify_writer_{run}", "reviewer": f"verify_reviewer_{run}"}
    for topic, group in ((config.INBOX_TOPIC, groups["planner"]), (config.TASKS_TOPIC, groups["writer"]), (config.DRAFTS_TOPIC, groups["reviewer"])):
        seed_group(group, topic)
    with tempfile.TemporaryDirectory() as tmp:
        cmds = [[sys.executable, "planner.py", "--brain", "rule", "--group", groups["planner"]],
                [sys.executable, "writer.py", "--brain", "rule", "--id", "verify-writer", "--group", groups["writer"], "--state-db", f"{tmp}/w.sqlite"],
                [sys.executable, "reviewer.py", "--group", groups["reviewer"]]]
        procs = [subprocess.Popen(c, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"}) for c in cmds]
        try:
            time.sleep(8)
            done = subprocess.run([sys.executable, "send_question.py", "--timeout", "60"], cwd=ROOT, capture_output=True, text=True,
                                  env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"})
        finally:
            for p in procs:
                p.terminate()
            for p in procs:
                p.wait(timeout=15)
    body = json.loads("{\n" + done.stdout.split("\n{\n", 1)[1]) if "\n{\n" in done.stdout else {}
    sent = [ln for ln in done.stderr.splitlines() + done.stdout.splitlines() if "sending question" in ln]
    sent_cid = sent[0].split("correlation_id=")[1].split()[0] if sent else None
    ok = done.returncode == 0 and body.get("status") == "approved" and body.get("correlation_id") == sent_cid and "Data Science" in (body.get("answer") or "")
    return ok, f"Planner -> Writer -> Reviewer through Kafka: status={body.get('status')}, correlation_id preserved={body.get('correlation_id') == sent_cid}"


def pipeline_topics_have_messages():
    ends = {t: sum(end_offsets(t).values()) for t in (config.INBOX_TOPIC, config.TASKS_TOPIC, config.DRAFTS_TOPIC, config.FINAL_TOPIC)}
    return all(n > 0 for n in ends.values()), f"messages ever written: {ends}"


# ---- Part 3: saved experiment data ------------------------------------------------------------------------
def duplicate_data():
    d = jload("reports/hw08/raw/failure_duplicate.json")
    return d["before"]["drafts_published"] == 2 and d["after"]["drafts_published"] == 1 and d["after"]["duplicate_skipped"] == 1, \
        f"replayed correlation_id -> drafts before={d['before']['drafts_published']}, after={d['after']['drafts_published']}"


def death_data():
    d = jload("reports/hw08/raw/failure_death.json")
    b, a = d["before"], d["after"]
    lag = lambda x: sum(r["lag"] or 0 for r in x["offsets_after_kill"]["rows"])  # noqa: E731
    ok = (not b["redelivered_after_restart"] and b["drafts_final"] == 0 and lag(b) == 0
          and a["redelivered_after_restart"] and a["drafts_final"] == 1 and lag(a) == 1)
    return ok, f"before: lag after kill {lag(b)}, redelivered={b['redelivered_after_restart']}, drafts={b['drafts_final']}; after: lag {lag(a)}, redelivered={a['redelivered_after_restart']}, drafts={a['drafts_final']}"


def poison_data():
    d = jload("reports/hw08/raw/failure_poison.json")
    b, a = d["before"], d["after"]
    rec = a["dead_letter_records"][0] if a["dead_letter_records"] else {}
    ok = (b["first_run_exit_code"] not in (0, None) and b["second_run_exit_code"] not in (0, None) and not b["good_message_processed"]
          and a["good_message_processed"] and rec.get("attempts") == 3 and rec.get("source_topic") == config.TASKS_TOPIC)
    return ok, f"before: crashes {b['first_run_exit_code']}/{b['second_run_exit_code']}, later message processed={b['good_message_processed']}; after: dead-lettered after {rec.get('attempts')} attempts, later message processed={a['good_message_processed']}"


def ordering_data():
    d = jload("reports/hw08/raw/failure_ordering.json")
    b, a = d["before"]["analysis"], d["after"]["analysis"]
    n = len(a["entities"])
    ok = (b["messages_processed"] == 20 and a["messages_processed"] == 20 and b["total_inversions"] > 0 and b["entities_in_one_partition"] < n
          and a["total_inversions"] == 0 and a["entities_in_one_partition"] == n and a["entities_in_order"] == n)
    return ok, f"no key: {b['total_inversions']} inversions, {b['entities_in_one_partition']}/{n} entities in one partition; keyed: {a['total_inversions']} inversions, {a['entities_in_one_partition']}/{n} in one partition"


# ---- repo hygiene -----------------------------------------------------------------------------------------
def offline_tests():
    r = subprocess.run([sys.executable, "tests_hw8.py"], cwd=ROOT, capture_output=True, text=True, timeout=300)
    last = [ln for ln in r.stdout.splitlines() if "tests passed" in ln]
    return r.returncode == 0 and bool(last), last[-1] if last else r.stdout[-200:]


def ruff_clean():
    r = subprocess.run([str(ROOT / ".venv/bin/ruff"), "check", "."], cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0, (r.stdout.strip().splitlines() or ["ruff: no output"])[-1]


for name, fn in [
    ("docker: s8360-kafka, s8360-worker and s8360-api are running", containers_running),
    ("Kafka topics exist with the required partition counts (tasks = 2)", topics_exist),
    ("CREATE_COURSE -> GET_COURSE round-trips through Kafka; errors keep the correlation_id", kafka_round_trip),
    ("FastAPI wrapper: POST/GET through Kafka, X-Correlation-ID preserved, 404 for unknown id", api_round_trip),
    ("Planner -> Writer -> Reviewer pipeline answers a question through Kafka only", pipeline),
    ("all four pipeline topics carry messages", pipeline_topics_have_messages),
    ("Part 3 duplicate delivery: replay creates 2 drafts before idempotency, 1 after", duplicate_data),
    ("Part 3 consumer death: message lost with early commit, redelivered and completed with commit-after", death_data),
    ("Part 3 poison message: crash loop before, retried 3x + dead-lettered + later message processed after", poison_data),
    ("Part 3 ordering: unkeyed messages interleave across partitions, keyed messages stay in one partition in order", ordering_data),
    ("offline test suite passes (no Kafka / network / model)", offline_tests),
    ("ruff passes on the repository", ruff_clean),
]:
    check(name, fn)
for f in ["reports/hw08/RUN_LOG.txt", "reports/hw08/METRICS.md", "reports/hw08/AI_USE.md", "reports/hw08/Pragada_HW8.pdf"]:
    check(f"{f} exists and is non-empty", lambda f=f: ((ROOT / f).exists() and (ROOT / f).stat().st_size > 0, f))

commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or None
passed = sum(c["passed"] for c in checks)
out = {"homework": "HW8", "sid4": SID4, "commit_hash": commit, "model": MODEL, "seed": config.SEED, "verify_seed": config.VERIFY_SEED,
       "timestamp": datetime.now(timezone.utc).isoformat(), "checks": checks, "passed": passed, "failed": len(checks) - passed,
       "total": len(checks), "overall": "PASS" if passed == len(checks) else "FAIL"}
(RAW.parent / "verification.json").write_text(json.dumps(out, indent=2))
print(f"\n{passed}/{len(checks)} checks passed.\nWrote reports/hw08/verification.json")
sys.exit(0 if passed == len(checks) else 1)
