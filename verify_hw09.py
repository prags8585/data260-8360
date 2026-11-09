#!/usr/bin/env python3
"""HW9 smoke test on the live system: Redis counter, semantic cache, saved sweep/stale/Part 4 data, tests, lint, deliverables."""
import hashlib
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from cache_svc import config  # noqa: E402
from cache_svc.course_db import CourseDB  # noqa: E402
from cache_svc.semantic_cache import SemanticCache  # noqa: E402

RAW = ROOT / "reports/hw09/raw"
API = f"http://127.0.0.1:{config.PORT_BASE}"
MODEL = "qwen3:8b via Ollama (temperature 0, seed 8360); embeddings sentence-transformers/all-MiniLM-L6-v2"
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


def containers_running():
    out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True).stdout.split()
    needed = ["s8360-redis", "s8360-kafka", "s8360-mysql"]
    return all(n in out for n in needed), f"running: {[n for n in needed if n in out]}"


def redis_has_search():
    cache = SemanticCache()
    cache.ensure_index()
    info = cache.search.info()
    modules = [m[b"name"].decode() for m in cache.client.module_list()]
    return "search" in modules and info["index_name"] in (config.INDEX_NAME, config.INDEX_NAME.encode()), f"modules {modules}; index {config.INDEX_NAME} on {config.ENTRY_PREFIX}*"


def views_column():
    from sqlalchemy import inspect

    from db import engine
    return "views" in [c["name"] for c in inspect(engine).get_columns("courses")], "courses.views exists"


def counter_syncs():
    db = CourseDB()
    course_id = 1
    key = config.views_key(course_id)
    from sqlalchemy import text

    from db import engine
    with engine.begin() as connection:
        saved = connection.execute(text("SELECT views FROM courses WHERE id = :i"), {"i": course_id}).scalar_one()
        connection.execute(text("UPDATE courses SET views = 0 WHERE id = :i"), {"i": course_id})
    db.redis_client.delete(key)
    totals = [db.increment_course_views(course_id) for _ in range(12)]
    with engine.connect() as connection:
        synced = connection.execute(text("SELECT views FROM courses WHERE id = :i"), {"i": course_id}).scalar_one()
    in_redis = int(db.redis_client.get(key))
    db.redis_client.delete(key)
    with engine.begin() as connection:
        connection.execute(text("UPDATE courses SET views = :v WHERE id = :i"), {"v": saved, "i": course_id})
    return totals == list(range(1, 13)) and synced == 10 and in_redis == 12, f"totals 1..12, Redis {in_redis}, MySQL synced at 10 -> {synced}"


def live_cache_round_trip():
    question = f"How many seats are available in DATA-260? (check {uuid.uuid4().hex[:6]})"
    client = httpx.Client(base_url=API, timeout=300)
    first = client.post("/ask", json={"question": question}).json()
    second = client.post("/ask", json={"question": question}).json()
    key = first.get("cache_key")
    if key:
        SemanticCache().delete(key)
    ok = (first["is_cached"] is False and first["status"] == "approved" and second["is_cached"] is True and second["similarity"] >= 0.99
          and second["answer"] == first["answer"] and second["latency_ms"] < first["latency_ms"])
    return ok, f"miss {first['latency_ms']} ms -> hit {second['latency_ms']} ms, similarity {second['similarity']}, same answer"


def sweep_data():
    d = jload("reports/hw09/raw/threshold_sweep.json")
    t = d["thresholds"]
    ok = sorted(t) == ["0.75", "0.80", "0.85", "0.90", "0.95"] and all(len(v["cases"]) == 40 for v in t.values())
    hit_rates = [t[k]["summary"]["hit_rate"] for k in sorted(t)]
    ok = ok and hit_rates == sorted(hit_rates, reverse=True)  # a higher threshold can only lower the hit rate
    return ok, "5 thresholds x 40 cases; hit rate " + " >= ".join(f"{h:.0%}" for h in hit_rates)


def cases_committed_before_sweep():
    d = jload("reports/hw09/raw/threshold_sweep.json")
    sha = hashlib.sha256((ROOT / "cache_cases.yaml").read_bytes()).hexdigest()
    first_commit = int(subprocess.run(["git", "log", "--reverse", "--format=%ct", "--", "cache_cases.yaml"], cwd=ROOT, capture_output=True, text=True).stdout.split()[0])
    started = datetime.fromisoformat(d["started"]).timestamp()
    return sha == d["cache_cases_sha256"] and first_commit < started, f"file unchanged since the sweep (sha256 {sha[:12]}...); first commit {datetime.fromtimestamp(first_commit):%H:%M:%S} before the sweep {d['started'][-8:]}"


def cases_file():
    spec = yaml.safe_load((ROOT / "cache_cases.yaml").read_text())
    cats = {c["category"] for c in spec["cases"]}
    return len(spec["cases"]) == 40 and len(cats) == 4, f"{len(spec['cases'])} cases in {len(cats)} categories"


def stale_data():
    d = jload("reports/hw09/raw/stale_demo.json")
    ok = d["ok"] and d["stale_hit"]["is_cached"] and not d["after_invalidation"]["is_cached"] and d["after_invalidation"]["stale_invalidated"]
    return ok, f"seats {d['seats_before']} -> {d['seats_after']}: stale hit returned {d['stale_hit']['answer']!r}; after invalidation {d['after_invalidation']['answer']!r}"


def part4_inputs():
    sets = {n: jload(f"part4/{n}.json") for n in ("training_data", "validation_data", "test_data")}
    ok = all(set(i) == {"id", "question"} for items in sets.values() for i in items)
    qs = [i["question"] for items in sets.values() for i in items]
    ok = ok and len(qs) == len(set(qs))
    ref = jload("part4/reference_data.json")
    return ok and len(ref["courses"]) == 6, f"{ {n: len(v) for n, v in sets.items()} } questions, inputs only, no overlap; {len(ref['courses'])} reference courses"


def part4_lessons():
    lessons = jload("part4/lessons.json")
    ok = all(set(row) == {"lesson_id", "failure_pattern", "correction", "created_at", "use_count"} for row in lessons) and len(lessons) >= 1
    return ok, f"{len(lessons)} validated lessons with the 5 required fields; use counts {[row['use_count'] for row in lessons]}"


def part4_final():
    d = jload("reports/hw09/raw/part4_final.json")
    names = ["Baseline", "Evaluator Repair", "Lesson Memory", "Validated Improvement"]
    ok = list(d) == names and all(v["summary"]["questions"] == 18 and v["summary"]["correct"] + v["summary"]["incorrect"] == 18 for v in d.values())
    ok = ok and d["Baseline"]["summary"]["average_attempts"] == 1.0 and all(v["summary"]["average_attempts"] <= 2.0 for v in d.values())
    row = {n: f"{v['summary']['correct']}/18 @ {v['summary']['average_attempts']} attempts" for n, v in d.items()}
    return ok, str(row)


def part4_split_discipline():
    mine, validation = jload("reports/hw09/raw/part4_mine.json"), jload("reports/hw09/raw/part4_validation.json")
    mined_ids = {r["id"] for r in mine["results"]}
    validated_ids = {r["id"] for entry in validation["log"] for r in entry["results_after"]}
    ok = all(i.startswith("tr") for i in mined_ids) and all(i.startswith("va") for i in validated_ids)
    return ok, f"lessons were mined on training ids only ({len(mined_ids)}) and validated on validation ids only ({len(validated_ids)}); test_data.json is used only by the final run"


def offline_tests():
    r = subprocess.run([sys.executable, "tests_hw9.py"], cwd=ROOT, capture_output=True, text=True, timeout=300)
    last = [ln for ln in r.stdout.splitlines() if "tests passed" in ln]
    return r.returncode == 0 and bool(last), last[-1] if last else r.stdout[-200:]


def ruff_clean():
    r = subprocess.run([str(ROOT / ".venv/bin/ruff"), "check", "."], cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0, (r.stdout.strip().splitlines() or ["ruff: no output"])[-1]


for name, fn in [
    ("docker: s8360-redis (Redis Stack), s8360-kafka and s8360-mysql are running", containers_running),
    ("Redis has the search module and the vector index exists", redis_has_search),
    ("courses.views column exists in s8360_rel", views_column),
    ("Part 1: increment_course_views returns the running total and syncs to MySQL every 10th increment", counter_syncs),
    ("Part 2: live POST /ask - miss runs the agents, the repeated question is a cache hit with similarity and latency", live_cache_round_trip),
    ("cache_cases.yaml has 40 labeled cases (4 categories x 10)", cases_file),
    ("Part 3: threshold sweep saved (5 thresholds x 40 cases)", sweep_data),
    ("Part 3: cache_cases.yaml was committed before the sweep and is unchanged since", cases_committed_before_sweep),
    ("Part 3.5: stale hit shown, then corrected by the data-version invalidation", stale_data),
    ("Part 4: input files hold only questions, no overlap, reference dataset present", part4_inputs),
    ("Part 4: lessons.json entries have the required fields", part4_lessons),
    ("Part 4: lessons mined on training only, validated on validation only", part4_split_discipline),
    ("Part 4: four variants evaluated on the same 18 test questions, at most 2 attempts", part4_final),
    ("offline test suite passes (no Kafka / Redis / network / model)", offline_tests),
    ("ruff passes on the repository", ruff_clean),
]:
    check(name, fn)
for f in ["reports/hw09/RUN_LOG.txt", "reports/hw09/METRICS.md", "reports/hw09/AI_USE.md|AI_Usage.md", "reports/hw09/Pragada_HW9.pdf"]:
    names = [f.rsplit("/", 1)[0] + "/" + n for n in f.rsplit("/", 1)[1].split("|")]
    check(f"{names[0]} exists and is non-empty", lambda names=names: (any((ROOT / n).exists() and (ROOT / n).stat().st_size > 0 for n in names), " or ".join(names)))

commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or None
passed = sum(c["passed"] for c in checks)
out = {"homework": "HW9", "sid4": config.PREFIX[1:], "commit_hash": commit, "model": MODEL, "seed": config.SEED,
       "timestamp": datetime.now(timezone.utc).isoformat(), "checks": checks, "passed": passed, "failed": len(checks) - passed,
       "total": len(checks), "overall": "PASS" if passed == len(checks) else "FAIL"}
(ROOT / "reports/hw09/verification.json").write_text(json.dumps(out, indent=2))
print(f"\n{passed}/{len(checks)} checks passed.\nWrote reports/hw09/verification.json")
sys.exit(0 if passed == len(checks) else 1)
