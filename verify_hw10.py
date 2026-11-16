#!/usr/bin/env python3
"""HW10 smoke test: the live services, the span file and trace propagation, the three required traces, the evaluator results, the frozen judge-validation
files, the latency table, the Streamlit pages, the offline tests, lint and the deliverables. Writes reports/hw10/verification.json."""
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from scipy.stats import spearmanr  # noqa: E402

from cache_svc import config  # noqa: E402
from tracing.store import by_trace, load_spans, trace_path  # noqa: E402

RAW = ROOT / "reports/hw10/raw"
API = f"http://127.0.0.1:{config.PORT_BASE}"
MODEL = "qwen3:8b via Ollama (temperature 0, seed 8360); judge: DeepEval GEval on the same local model"
REQUIRED_SPAN_FIELDS = ("trace_id", "stage", "start", "end", "status", "error", "duration_ms")
MISS_STAGES = ["request", "cache_lookup", "queue_inbox", "planner", "queue_tasks", "writer", "queue_drafts", "reviewer", "queue_final"]
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


def jsonl(path):
    return [json.loads(line) for line in (ROOT / path).read_text().splitlines() if line.strip()]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def containers_running():
    out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True).stdout.split()
    needed = ["s8360-redis", "s8360-kafka", "s8360-mysql"]
    return all(n in out for n in needed), f"running: {[n for n in needed if n in out]}"


def services_up():
    health = httpx.get(f"{API}/health", timeout=10).json()
    tags = httpx.get("http://127.0.0.1:11434/api/tags", timeout=10).json()
    models = [m["name"] for m in tags["models"]]
    return health["status"] == "ok" and "qwen3:8b" in models, f"ingress {API} ok ({health['cached_entries']} cached entries); Ollama has {'qwen3:8b' if 'qwen3:8b' in models else 'NO qwen3:8b'}"


def spans_well_formed():
    spans = load_spans(RAW / "spans.jsonl")
    missing = [s for s in spans if any(f not in s for f in REQUIRED_SPAN_FIELDS)]
    return bool(spans) and not missing and all(s["status"] in ("ok", "error") for s in spans), f"{len(spans)} spans, every one has {', '.join(REQUIRED_SPAN_FIELDS)}; statuses ok/error only"


def trace_propagation():
    latency = jload("reports/hw10/raw/latency_requests.json")
    traces = by_trace(load_spans(RAW / "spans.jsonl"))
    evals = {r["trace_id"]: r for r in jsonl("reports/hw10/raw/latency_evals.jsonl")}
    bad = []
    for m in latency["misses"]:
        stages = {s["stage"] for s in traces.get(m["trace_id"], [])}
        if not set(MISS_STAGES + ["evaluation"]) <= stages:
            bad.append(m["trace_id"])
        ev = evals.get(m["trace_id"])
        if ev is None or not all(ev["messages"][k]["correlation_id"] == m["trace_id"] for k in ("plan", "draft", "final")):
            bad.append(m["trace_id"])
    return not bad, f"{len(latency['misses'])} cache-miss traces carry cache_lookup, queue_inbox, planner, queue_tasks, writer, queue_drafts, reviewer, queue_final and evaluation spans, and the plan, draft and final messages share the trace_id (= HW8 correlation_id)"


def required_traces():
    examples = jload("reports/hw10/raw/trace_examples.json")
    traces = by_trace(load_spans(RAW / "spans.jsonl"))
    hit, miss, failed = (traces[examples[k]["trace_id"]] for k in ("cache_hit", "cache_miss", "failed"))
    ok = (trace_path(hit) == "cache_hit" and not any(s["stage"] in ("planner", "writer", "reviewer") for s in hit)
          and trace_path(miss) == "cache_miss" and all(s["status"] == "ok" for s in miss) and {"planner", "writer", "reviewer"} <= {s["stage"] for s in miss}
          and trace_path(failed) == "failed" and any(s["stage"] == "writer" and s["status"] == "error" for s in failed))
    err = next(s["error"] for s in failed if s["stage"] == "writer" and s["status"] == "error")
    return ok, f"cache hit {examples['cache_hit']['trace_id'][:8]}..., cache miss {examples['cache_miss']['trace_id'][:8]}..., failed {examples['failed']['trace_id'][:8]}... (writer: {err[:60]})"


def part2_evals():
    records = jsonl("reports/hw10/raw/part2_evals.jsonl")
    keys = ("plan_quality", "writer_helpfulness", "final_answer_helpfulness")
    ok = len(records) >= 1 and all(all(1 <= r[k]["score"] <= 5 and r[k]["reason"] for k in keys) for r in records)
    ok = ok and all(r["messages"]["plan"]["correlation_id"] == r["messages"]["draft"]["correlation_id"] == r["messages"]["final"]["correlation_id"] == r["trace_id"] for r in records)
    ok = ok and all(r["final_vs_draft"]["interpretation"] and "difference" in r["final_vs_draft"] and r["judge"]["temperature"] == 0.0 for r in records)
    ok = ok and all(all({"topic", "partition", "offset", "timestamp_ms"} <= set(r["message_metadata"][k]) for k in ("plan", "draft", "final")) for r in records)
    ok = ok and all(r["criteria"]["writer_helpfulness"]["evaluation_steps"] and len(r["criteria"]["rubric"]) == 5 for r in records)
    return ok, f"{len(records)} requests scored on the four criteria (1-5); plan, draft and final share the correlation_id; judge settings, original messages, Kafka topic/partition/offset/timestamp and the criteria text stored"


def frozen_files():
    cases = jload("eval_cases.json")["cases"]
    labels = list(csv.DictReader((ROOT / "human_labels.csv").open()))
    ok = len(cases) == 20 and [r["case_id"] for r in labels] == [c["case_id"] for c in cases] and all(r["helpfulness_label"].strip() in "12345" and r["helpfulness_label"].strip() for r in labels)
    dist = {k: sum(r["helpfulness_label"].strip() == str(k) for r in labels) for k in range(1, 6)}
    return ok, f"20 drafts, 20 hand-assigned labels (distribution {dist})"


def committed_before_judge():
    validation = jload("reports/hw10/raw/judge_validation.json")
    frozen = validation["frozen_files"]
    unchanged = not git("status", "--porcelain", "--", "eval_cases.json", "human_labels.csv")
    current = git("log", "-1", "--format=%H", "--", "eval_cases.json", "human_labels.csv")
    out_time = datetime.fromtimestamp((RAW / "judge_validation.json").stat().st_mtime, timezone.utc)
    committed = datetime.fromisoformat(frozen["committed_at"])
    return unchanged and current == frozen["commit"] and committed < out_time, f"committed in {frozen['commit'][:7]} at {frozen['committed_at']}, before the judge scores were written ({out_time.isoformat(timespec='seconds')}); unchanged since"


def judge_statistics_recompute():
    v = jload("reports/hw10/raw/judge_validation.json")
    human = [c["human"] for c in v["cases"]]
    run1 = [c["judge_run1"] for c in v["cases"]]
    rho = spearmanr(human, run1).statistic
    mad = sum(abs(a - b) for a, b in zip(human, run1)) / len(human)
    ok = len(human) == 20 and abs(rho - v["spearman"]["rho"]) < 1e-9 and abs(mad - v["mean_absolute_difference"]) < 1e-9 and all(f"judge_run{k}" in v["cases"][0] for k in (1, 2, 3))
    return ok, f"Spearman {rho:.3f} and mean absolute difference {mad:.3f} recomputed from the per-case data of 3 runs"


def latency_table():
    t = jload("reports/hw10/raw/latency_table.json")
    data = jload("reports/hw10/raw/latency_requests.json")
    stages = [r["stage"] for r in t["table"]]
    ok = t["requests"] == 50 and len(data["misses"]) == 50 and not any(m["is_cached"] for m in data["misses"]) and all(r["p50_ms"] <= r["p95_ms"] for r in t["table"])
    ok = ok and stages == ["Cache lookup", "Planner", "Writer", "Reviewer", "Queue wait (total)", "Evaluation"]
    return ok, f"50 confirmed cache misses ({len(data['discarded_cache_hits'])} candidate questions were discarded because the cache answered); p50 <= p95 for all six stages; cache-hit p50 {t['cache_hit']['p50_ms']} ms (n={t['cache_hit']['n']})"


def dashboard_renders():
    from streamlit.testing.v1 import AppTest
    os.environ["DASHBOARD_SPANS"] = str(RAW / "spans.jsonl")
    try:
        at = AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=120).run()
        problems = [e.value for e in at.exception]
        for page in ("Evaluation", "Trace lookup"):
            at.sidebar.radio[0].set_value(page).run()
            problems += [e.value for e in at.exception]
        examples = jload("reports/hw10/raw/trace_examples.json")
        at.text_input[0].set_value(examples["failed"]["trace_id"]).run()
        found = any("FAILED trace" in e.value for e in at.error)
    finally:
        os.environ.pop("DASHBOARD_SPANS", None)
    return not problems and found, "Summary, Evaluation and Trace lookup render from the committed spans; the failed example trace is looked up by trace_id"


def offline_tests():
    results = []
    for name in ("tests_hw10.py", "tests_hw9.py", "tests_hw8.py"):
        r = subprocess.run([sys.executable, name], cwd=ROOT, capture_output=True, text=True, timeout=600)
        last = [ln for ln in r.stdout.splitlines() if "tests passed" in ln]
        results.append((r.returncode == 0 and bool(last), f"{name}: {last[-1] if last else r.stdout[-120:]}"))
    return all(ok for ok, _ in results), "; ".join(text for _, text in results)


def ruff_clean():
    r = subprocess.run([str(ROOT / ".venv/bin/ruff"), "check", "."], cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0, (r.stdout.strip().splitlines() or ["ruff: no output"])[-1]


def pdf_pages():
    out = subprocess.run(["pdfinfo", str(ROOT / "reports/hw10/Pragada_HW10.pdf")], capture_output=True, text=True).stdout
    pages = int(next(line.split()[-1] for line in out.splitlines() if line.startswith("Pages:")))
    return pages <= 35, f"{pages} pages (limit 35)"


for name, fn in [
    ("docker: s8360-redis, s8360-kafka and s8360-mysql are running", containers_running),
    ("the ingress API answers /health and Ollama serves qwen3:8b", services_up),
    ("Part 4.1: every span is valid JSON with trace_id, stage, start, end, status and error", spans_well_formed),
    ("Part 4.1: trace_id (= correlation_id) is propagated through cache lookup, inbox, tasks, drafts, final and the evaluator", trace_propagation),
    ("Part 4.2: one cache-hit, one successful cache-miss and one failed trace exist, with the failing stage identified", required_traces),
    ("Part 2: evaluation results for the four criteria, joined by correlation_id", part2_evals),
    ("Part 3.1: eval_cases.json (20 drafts) and human_labels.csv (20 hand labels) are complete", frozen_files),
    ("Part 3.1: both files were committed before any judge score was computed and are unchanged", committed_before_judge),
    ("Part 3.2/3.3: Spearman and mean absolute difference can be recomputed from the raw per-case data (3 runs)", judge_statistics_recompute),
    ("Part 4.3: 50 confirmed cache misses, six-stage p50/p95 table, cache-hit latency kept separate", latency_table),
    ("Part 1: the three Streamlit pages render and look up a trace", dashboard_renders),
    ("offline tests pass (HW10, HW9, HW8; no Kafka / Redis / network / model)", offline_tests),
    ("ruff passes on the repository", ruff_clean),
]:
    check(name, fn)
for f in ["reports/hw10/RUN_LOG.txt", "reports/hw10/METRICS.md", "reports/hw10/AI_USE.md|AI_Usage.md", "reports/hw10/Pragada_HW10.pdf"]:
    names = [f.rsplit("/", 1)[0] + "/" + n for n in f.rsplit("/", 1)[1].split("|")]
    check(f"{names[0]} exists and is non-empty", lambda names=names: (any((ROOT / n).exists() and (ROOT / n).stat().st_size > 0 for n in names), " or ".join(names)))
check("the PDF is within the 35-page limit", pdf_pages)

commit = git("rev-parse", "HEAD") or None
passed = sum(c["passed"] for c in checks)
out = {"homework": "HW10", "sid4": config.PREFIX[1:], "commit_hash": commit, "model": MODEL, "seed": config.SEED,
       "timestamp": datetime.now(timezone.utc).isoformat(), "checks": checks, "passed": passed, "failed": len(checks) - passed,
       "total": len(checks), "overall": "PASS" if passed == len(checks) else "FAIL"}
(ROOT / "reports/hw10").mkdir(parents=True, exist_ok=True)
(ROOT / "reports/hw10/verification.json").write_text(json.dumps(out, indent=2))
print(f"\n{passed}/{len(checks)} checks passed.\nWrote reports/hw10/verification.json")
sys.exit(0 if passed == len(checks) else 1)
