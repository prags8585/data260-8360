"""Offline tests for HW10: tracing, the evaluator's join and scoring logic, the judge wrapper (with a fake Ollama), the validation statistics and the
Streamlit pages. No Kafka, Redis, MySQL, network or model is used."""
import csv
import json
import logging
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
_TMP = tempfile.mkdtemp(prefix="hw10_tests_")
os.environ["TRACE_FILE"] = str(Path(_TMP) / "spans.jsonl")  # nothing in this file touches the real span file

from cache_svc.ingress import QAIngress  # noqa: E402
from dashboard import data as dash  # noqa: E402
from evaluation import judge as judge_module  # noqa: E402
from evaluation import pipeline_eval  # noqa: E402
from evaluation.validation import agreement, repeatability, spearman, verdict  # noqa: E402
from tests_hw9 import FakeCache, make_db  # noqa: E402
from tracing import spans as sp  # noqa: E402
from tracing import store  # noqa: E402

ROOT = Path(__file__).resolve().parent
REAL_SLEEP = time.sleep  # the HW8 Writer fakes replace time.sleep for the whole process; every test gets the real one back


@pytest.fixture(autouse=True)
def _restore_real_sleep():
    yield
    time.sleep = REAL_SLEEP


def fresh_trace_file() -> Path:
    path = Path(tempfile.mkdtemp(dir=_TMP)) / "spans.jsonl"
    os.environ["TRACE_FILE"] = str(path)
    return path


# --- tracing ------------------------------------------------------------------------------------------------------------

def test_a_span_has_the_required_fields_and_trace_id_is_the_correlation_id():
    path = fresh_trace_file()
    sp.emit_span("corr-1", "planner", 100.0, 100.25, "ok", None, extra="x")
    [line] = path.read_text().splitlines()
    span = json.loads(line)
    for field in ("trace_id", "stage", "start", "end", "status", "error", "duration_ms", "start_ts", "end_ts"):
        assert field in span
    assert span["trace_id"] == "corr-1" and span["duration_ms"] == 250.0 and span["status"] == "ok" and span["error"] is None and span["extra"] == "x"
    assert span["start"].endswith("Z") and "T" in span["start"]


def test_no_trace_id_means_no_span_and_an_unwritable_file_never_raises():
    path = fresh_trace_file()
    assert sp.emit_span(None, "planner", 1, 2) is None and not path.exists()
    os.environ["TRACE_FILE"] = "/proc/definitely/not/writable/spans.jsonl"
    assert sp.emit_span("c", "planner", 1, 2) is None  # swallowed: tracing must never break the pipeline
    fresh_trace_file()


def test_span_context_manager_records_an_error_and_reraises_it():
    path = fresh_trace_file()
    try:
        with sp.span("c1", "writer") as handle:
            handle.set(attempts=3)
            raise ValueError("boom\nsecond line")
    except ValueError:
        pass
    span = json.loads(path.read_text())
    assert span["status"] == "error" and span["error"] == "ValueError: boom" and span["attempts"] == 3  # one line only


def test_queue_span_runs_from_the_kafka_timestamp_to_the_start_of_processing():
    path = fresh_trace_file()

    class Msg:
        def timestamp(self): return (1, 1_000_000)  # CreateTime, ms
        def topic(self): return "s8360_tasks"

    sp.queue_span("c1", "queue_tasks", Msg(), 1003.5, service="writer")
    span = json.loads(path.read_text())
    assert span["stage"] == "queue_tasks" and span["duration_ms"] == 3500.0 and span["topic"] == "s8360_tasks"

    class NoTime:
        def timestamp(self): raise RuntimeError("no timestamp")

    assert sp.queue_span("c1", "queue_tasks", NoTime(), 5.0) is None


def test_concurrent_writers_never_interleave_lines():
    path = fresh_trace_file()

    def work(n):
        for i in range(60):
            sp.emit_span(f"t{n}", "writer", 1.0, 2.0, pad="x" * 400, i=i)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    lines = path.read_text().splitlines()
    assert len(lines) == 480 and all(json.loads(line)["stage"] == "writer" for line in lines)


def span_row(trace, stage, start, end, status="ok", **kw):
    return {"trace_id": trace, "stage": stage, "start_ts": start, "end_ts": end, "start": sp.iso(start), "end": sp.iso(end), "duration_ms": round((end - start) * 1000, 2),
            "status": status, "error": kw.pop("error", None), **kw}


def miss_trace(trace, t0, total=10.0, planner=3.0, writer_s=5.0, status="ok"):
    return [span_row(trace, "request", t0, t0 + total, status, path="cache_miss", review_status="approved"),
            span_row(trace, "cache_lookup", t0, t0 + 0.02, hit=False, similarity=0.3),
            span_row(trace, "queue_inbox", t0 + 0.02, t0 + 0.05), span_row(trace, "planner", t0 + 0.05, t0 + 0.05 + planner),
            span_row(trace, "queue_tasks", t0 + 0.05 + planner, t0 + 0.07 + planner),
            span_row(trace, "writer", t0 + 0.07 + planner, t0 + 0.07 + planner + writer_s), span_row(trace, "queue_drafts", t0 + 0.2, t0 + 0.23),
            span_row(trace, "reviewer", t0 + 0.23, t0 + 0.24), span_row(trace, "queue_final", t0 + 0.24, t0 + 0.26)]


def hit_trace(trace, t0, total=0.03):
    return [span_row(trace, "request", t0, t0 + total, path="cache_hit", review_status="approved"), span_row(trace, "cache_lookup", t0, t0 + total - 0.001, hit=True, similarity=1.0)]


def test_trace_paths_are_hit_miss_or_failed_and_the_failing_stage_is_the_root_cause():
    assert store.trace_path(store.ordered(hit_trace("h", 0))) == "cache_hit"
    assert store.trace_path(store.ordered(miss_trace("m", 0))) == "cache_miss"
    failed = miss_trace("f", 0)
    failed[0]["status"] = "error"
    failed[5].update(status="error", error="OperationalError: mysql down")
    failed.append(span_row("f", "agent_round_trip", 0.02, 9, "error", error="TimeoutError"))
    ordered = store.ordered(failed)
    assert store.trace_path(ordered) == "failed"
    assert store.failing_stage(ordered)["stage"] == "writer"  # not 'request' / 'agent_round_trip', which only fail BECAUSE the writer did
    assert store.trace_summary(ordered)["error"] == "OperationalError: mysql down"


def test_spans_are_returned_in_stage_order_even_when_written_out_of_order():
    spans = list(reversed(miss_trace("m", 100.0)))
    assert [s["stage"] for s in store.ordered(spans)][:3] == ["request", "cache_lookup", "queue_inbox"]  # request and lookup start together: request first


def test_a_half_written_line_in_the_span_file_is_skipped():
    path = fresh_trace_file()
    sp.emit_span("c1", "planner", 1, 2)
    with open(path, "a") as handle:
        handle.write('{"trace_id": "c2", "stage": "pla')
    assert len(store.load_spans(path)) == 1


def test_percentile_matches_numpy():
    values = [3.0, 9.0, 1.0, 7.0, 5.0, 11.0, 2.0]
    for q in (50, 95):
        assert abs(store.percentile(values, q) - float(np.percentile(values, q))) < 1e-9
    assert store.percentile([], 50) is None


# --- ingress spans -----------------------------------------------------------------------------------------------------

def make_traced_ingress(similarity: float, take_trace: bool):
    import cache_svc.ingress as ingress_module
    ingress_module.embed = lambda texts: [np.zeros(4, dtype=np.float32) for _ in texts]
    seen = {}

    def agent_with_trace(question, trace_id=None, timeout=None):
        seen["trace_id"], seen["timeout"] = trace_id, timeout
        return {"status": "approved", "answer": "agent answer", "correlation_id": trace_id}

    def agent_plain(question):  # the HW9 signature still works
        seen["plain"] = True
        return {"status": "approved", "answer": "agent answer", "correlation_id": "c"}

    cache = FakeCache()
    cache.entries["k0"] = {"query": "seed", "answer": "cached", "data_version": "v", "deps": "*"}
    cache.similarity = similarity
    db = make_db()
    db.data_version = lambda deps=None: "v"
    return QAIngress(cache, db, agent_with_trace if take_trace else agent_plain, threshold=0.9, validate_version=True), seen


def test_cache_hit_writes_a_cache_lookup_span_and_a_request_span_with_the_same_trace_id():
    path = fresh_trace_file()
    ingress, seen = make_traced_ingress(0.97, True)
    result = ingress.ask("q")
    spans = store.load_spans(path)
    assert result["is_cached"] and {s["trace_id"] for s in spans} == {result["trace_id"]} and "trace_id" not in seen
    assert [s["stage"] for s in store.ordered(spans)] == ["request", "cache_lookup"]
    lookup = next(s for s in spans if s["stage"] == "cache_lookup")
    assert lookup["hit"] is True and lookup["similarity"] == 0.97
    assert next(s for s in spans if s["stage"] == "request")["path"] == "cache_hit"


def test_cache_miss_passes_the_same_trace_id_to_the_agent_and_records_miss_spans():
    path = fresh_trace_file()
    ingress, seen = make_traced_ingress(0.2, True)
    result = ingress.ask("brand new question", timeout_s=30)
    spans = store.load_spans(path)
    assert not result["is_cached"] and seen["trace_id"] == result["trace_id"] and seen["timeout"] == 30  # no second identifier
    stages = {s["stage"] for s in spans}
    assert {"request", "cache_lookup", "cache_store"} <= stages
    assert next(s for s in spans if s["stage"] == "cache_lookup")["hit"] is False and next(s for s in spans if s["stage"] == "request")["path"] == "cache_miss"


def test_an_agent_timeout_makes_the_request_span_an_error():
    path = fresh_trace_file()
    ingress, _ = make_traced_ingress(0.1, True)
    ingress.agent = lambda question, trace_id=None, timeout=None: {"status": "timeout", "answer": None, "correlation_id": trace_id}
    ingress.ask("q")
    request = next(s for s in store.load_spans(path) if s["stage"] == "request")
    assert request["status"] == "error" and "did not answer" in request["error"]


def test_hw9_style_agent_without_a_trace_parameter_still_works():
    fresh_trace_file()
    ingress, seen = make_traced_ingress(0.1, False)
    assert ingress.ask("q")["answer"] == "agent answer" and seen["plain"]


# --- the Writer's span on failure (reusing the HW8 fakes) -------------------------------------------------------------

def test_writer_failure_after_all_attempts_writes_an_error_span_and_dead_letters():
    import tests_hw8 as hw8
    path = fresh_trace_file()
    hooks = hw8.patched_writer()
    bad = hw8.FakeMsg(b'{"correlation_id": "c-bad", "question": "q", "plan": "not a list"}', 3, key=b"c-bad")
    consumer, _, dead = hw8.run_writer(hooks, [bad], hw8.writer_args(), None)
    span = next(s for s in store.load_spans(path) if s["stage"] == "writer")
    assert span["trace_id"] == "c-bad" and span["status"] == "error" and span["attempts"] == 3 and span["dead_lettered"] and "plan" in span["error"]
    assert dead and consumer.committed == [3]


def test_writer_success_writes_an_ok_span():
    import tests_hw8 as hw8
    path = fresh_trace_file()
    hooks = hw8.patched_writer()
    hw8.run_writer(hooks, [hw8.FakeMsg(hw8.task_bytes("c-ok"), 1, key=b"c-ok")], hw8.writer_args(), None)
    span = next(s for s in store.load_spans(path) if s["stage"] == "writer")
    assert span["status"] == "ok" and span["trace_id"] == "c-ok" and span["error"] is None


# --- the evaluator: joining and scoring ------------------------------------------------------------------------------

def msgs(cid="c1", draft="Data Science has 105 seats.", answer="Data Science has 105 seats.", status="approved"):
    return ({"correlation_id": cid, "question": "q", "plan": ["a", "b"], "plan_source": "llm"},
            {"correlation_id": cid, "question": "q", "plan": ["a", "b"], "draft": draft, "facts": {"x": 1}},
            {"correlation_id": cid, "question": "q", "status": status, "answer": answer if status == "approved" else None})


def test_join_store_joins_plan_draft_and_final_by_correlation_id_and_counts_malformed_messages():
    store_ = pipeline_eval.JoinStore()
    plan, draft, final = msgs()
    assert store_.add("tasks", plan) == "c1" and not store_.complete("c1")
    assert store_.add("drafts", draft) == "c1" and store_.add("final", final) == "c1" and store_.complete("c1")
    assert store_.add("final", None) is None and store_.add("drafts", {"draft": "no id"}) is None and store_.add("tasks", {"correlation_id": "z"}) is None
    assert store_.add("drafts", {"correlation_id": "t", "draft": "x", "test": "ordering"}) is None  # HW8 failure-test traffic
    assert store_.skipped == 4 and store_.incomplete() == []
    store_.add("tasks", msgs("c2")[0])
    assert store_.incomplete() == ["c2"]


class FakeJudge:
    def __init__(self, scores):
        self.scores, self.calls = scores, []

    def get_model_name(self):
        return "fake-judge"


def patch_judge_one(scores, fail=()):
    def fake(key, judge, question, text, facts=None):
        judge.calls.append((key, text))
        if key in fail:
            return judge_module.Judgement(key, None, "", "RuntimeError: judge unavailable", 5.0)
        return judge_module.Judgement(key, scores[key], f"reason for {key}", None, 5.0)
    pipeline_eval.judge_one = fake


def test_evaluation_record_has_the_four_required_criteria_and_keeps_the_original_messages():
    path = fresh_trace_file()
    patch_judge_one({"plan_quality": 3, "writer_helpfulness": 4, "final_answer_helpfulness": 5})
    plan, draft, final = msgs()
    record = pipeline_eval.evaluate_trace("c1", plan, draft, final, FakeJudge(None))
    assert record["plan_quality"]["score"] == 3 and record["plan_quality"]["reason"] and record["plan_quality"]["plan"] == ["a", "b"]
    assert record["writer_helpfulness"]["score"] == 4 and record["writer_helpfulness"]["trace_id"] == "c1"
    assert record["final_answer_helpfulness"]["score"] == 5 and record["final_answer_helpfulness"]["final_answer"] == final["answer"]
    fvd = record["final_vs_draft"]
    assert (fvd["draft_score"], fvd["final_score"], fvd["difference"]) == (4, 5, 1) and "judge noise" in fvd["interpretation"]  # identical text, different score
    assert record["messages"] == {"plan": plan, "draft": draft, "final": final} and record["judge"]["temperature"] == 0.0 and not record["errors"]
    span = next(s for s in store.load_spans(path) if s["stage"] == "evaluation")
    assert span["trace_id"] == "c1" and span["status"] == "ok"


def test_the_record_keeps_kafka_metadata_and_the_criteria_text_needed_to_reproduce_the_scores():
    fresh_trace_file()
    patch_judge_one({"plan_quality": 3, "writer_helpfulness": 4, "final_answer_helpfulness": 5})
    plan, draft, final = msgs()
    store_ = pipeline_eval.JoinStore()
    store_.add("tasks", plan, 100.0, {"topic": "s8360_tasks", "partition": 1, "offset": 7, "timestamp_ms": 100000})
    store_.add("drafts", draft, 101.0, {"topic": "s8360_drafts", "partition": 0, "offset": 3, "timestamp_ms": 101000})
    store_.add("final", final, 102.0, {"topic": "s8360_final", "partition": 0, "offset": 9, "timestamp_ms": 102000})
    meta = {k: store_.__dict__[v]["c1"]["meta"] for k, v in (("plan", "plans"), ("draft", "drafts"), ("final", "finals"))}
    record = pipeline_eval.evaluate_trace("c1", plan, draft, final, FakeJudge(None), meta=meta)
    assert record["message_metadata"]["plan"] == {"topic": "s8360_tasks", "partition": 1, "offset": 7, "timestamp_ms": 100000}
    assert record["message_metadata"]["final"]["offset"] == 9
    assert record["criteria"]["writer_helpfulness"]["evaluation_steps"] and len(record["criteria"]["rubric"]) == 5


def test_a_rejected_draft_is_scored_as_no_answer_and_interpreted_honestly():
    fresh_trace_file()
    patch_judge_one({"plan_quality": 4, "writer_helpfulness": 2, "final_answer_helpfulness": 1})
    plan, draft, final = msgs(status="rejected")
    judge = FakeJudge(None)
    record = pipeline_eval.evaluate_trace("c1", plan, draft, final, judge)
    assert any(text == pipeline_eval.NO_ANSWER for key, text in judge.calls if key == "final_answer_helpfulness")
    assert record["final_vs_draft"]["difference"] == -1 and "rejected" in record["final_vs_draft"]["interpretation"]


def test_an_unavailable_judge_gives_none_scores_and_an_error_span_instead_of_an_exception():
    path = fresh_trace_file()
    patch_judge_one({"plan_quality": 3, "writer_helpfulness": 4, "final_answer_helpfulness": 5}, fail=("writer_helpfulness",))
    plan, draft, final = msgs()
    record = pipeline_eval.evaluate_trace("c1", plan, draft, final, FakeJudge(None))
    assert record["writer_helpfulness"]["score"] is None and "writer_helpfulness" in record["errors"] and record["final_vs_draft"]["difference"] is None
    assert "not comparable" in record["final_vs_draft"]["interpretation"].lower()
    assert next(s for s in store.load_spans(path) if s["stage"] == "evaluation")["status"] == "error"


def test_the_per_trace_deadline_stops_the_remaining_judge_calls():
    fresh_trace_file()
    patch_judge_one({"plan_quality": 3, "writer_helpfulness": 4, "final_answer_helpfulness": 5})
    plan, draft, final = msgs()
    record = pipeline_eval.evaluate_trace("c1", plan, draft, final, FakeJudge(None), deadline_s=-1.0)
    assert all(record[k]["score"] is None for k in ("plan_quality", "writer_helpfulness", "final_answer_helpfulness")) and "deadline" in record["errors"]["plan_quality"]


# --- the judge wrapper (a fake Ollama client) ---------------------------------------------------------------------------

class FakeOllama:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, 0

    def chat(self, **kwargs):
        self.calls += 1
        return self.behaviour(self.calls, kwargs)


def judge_with(behaviour, **settings):
    judge = judge_module.LocalOllamaJudge(settings or None)
    judge.model = FakeOllama(behaviour)
    return judge


def test_geval_score_is_returned_on_the_one_to_five_scale():
    judge_module.JUDGE_SETTINGS  # noqa: B018
    for score in (1, 3, 5):
        judge = judge_with(lambda n, kw, s=score: {"message": {"content": json.dumps({"score": s, "reason": "because"})}})
        result = judge_module.judge_one("writer_helpfulness", judge, "q?", "draft", "{}")
        assert result.error is None and result.score == score and result.reason == "because"


def test_judge_settings_are_the_documented_ones_and_reach_the_model_call():
    seen = {}

    def behaviour(n, kw):
        seen.update(kw)
        return {"message": {"content": json.dumps({"score": 4, "reason": "ok"})}}

    judge_module.judge_one("plan_quality", judge_with(behaviour), "q?", "1. a", None)
    assert seen["model"] == "qwen3:8b" and seen["options"]["temperature"] == 0.0 and seen["options"]["seed"] == 8360 and seen["think"] is False and seen["format"]


def test_a_hung_or_failing_judge_is_retried_once_then_reported_never_raised():
    def always_fails(n, kw):
        raise TimeoutError("ollama timed out")

    judge = judge_with(always_fails)
    result = judge_module.judge_one("writer_helpfulness", judge, "q?", "d", "{}")
    assert result.score is None and "judge unavailable after 2 attempts" in result.error and judge.model.calls == 2


def test_a_malformed_judge_reply_is_retried_and_a_second_good_reply_is_used():
    def flaky(n, kw):
        return {"message": {"content": "not json" if n == 1 else json.dumps({"score": 2, "reason": "fine"})}}

    result = judge_module.judge_one("writer_helpfulness", judge_with(flaky), "q?", "d", "{}")
    assert result.score == 2 and result.error is None


def test_the_judge_timeout_is_part_of_the_client_configuration():
    assert judge_module.JUDGE_SETTINGS["timeout_s"] == 90 and judge_module.JUDGE_SETTINGS["max_attempts"] == 2


# --- judge validation statistics ---------------------------------------------------------------------------------------

def test_spearman_known_values_and_the_constant_case():
    assert abs(spearman([1, 2, 3, 4, 5], [2, 3, 4, 5, 5])["rho"] - 0.9746794) < 1e-6
    assert abs(spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])["rho"] + 1.0) < 1e-9
    undefined = spearman([1, 2, 3], [4, 4, 4])
    assert undefined["rho"] is None and "constant" in undefined["note"]


def test_agreement_statistics():
    a = agreement([5, 4, 3, 2, 1], [5, 5, 3, 4, 1])
    assert a["mean_absolute_difference"] == 0.6 and a["exact_agreement"] == 0.6 and a["within_one"] == 0.8 and a["bias"] == 0.6 and a["max_absolute_difference"] == 2


def test_repeatability_counts_changes_between_runs():
    r = repeatability([[1, 2, 3, 4], [1, 2, 4, 4], [1, 3, 4, 4]])
    assert r["runs"] == 3 and r["cases_with_any_change"] == 2 and r["changed_cases"] == [1, 2] and r["max_abs_change"] == 1
    assert abs(r["mean_abs_change"] - 4 / 12) < 1e-9
    same = repeatability([[1, 2], [1, 2], [1, 2]])
    assert same["cases_with_any_change"] == 0 and same["max_abs_change"] == 0 and same["mean_abs_change"] == 0


def test_verdict_refuses_a_deployment_gate_with_few_cases_even_when_everything_else_is_perfect():
    perfect = {"cases_with_any_change": 0}
    text = verdict(0.95, 0.2, 0.0, perfect, 20)
    assert text.startswith("I would NOT trust") and "far too few" in text and "rank agreement" not in text
    assert verdict(0.95, 0.2, 0.0, perfect, 150).startswith("The judge meets")
    assert "undefined" in verdict(None, 0.2, 0.0, perfect, 150)


def test_judge_validation_refuses_missing_or_invalid_human_labels():
    import importlib
    script = importlib.import_module("scripts.hw10_judge_validation")
    original = script.ROOT
    script.ROOT = Path(tempfile.mkdtemp(dir=_TMP))
    try:
        (script.ROOT / "human_labels.csv").write_text("case_id,helpfulness_label,labeled_at\ne01,4,\ne02,,\ne03,9,\n")
        for cid in ("e02", "e03", "e04"):
            try:
                script.load_labels([cid])
                raise AssertionError(f"{cid} should have been refused")
            except SystemExit as exc:
                assert "every case needs a hand-assigned integer label" in str(exc)
        assert script.load_labels(["e01"]) == {"e01": 4}
    finally:
        script.ROOT = original


# --- the frozen evaluation files ----------------------------------------------------------------------------------------

def test_eval_cases_has_20_writer_drafts_and_human_labels_cover_the_same_cases():
    doc = json.loads((ROOT / "eval_cases.json").read_text())
    cases = doc["cases"]
    assert len(cases) == 20 and len({c["case_id"] for c in cases}) == 20
    for c in cases:
        assert set(c) >= {"case_id", "question", "draft", "facts", "plan", "writer_brain"} and c["draft"].strip()
    rows = list(csv.DictReader((ROOT / "human_labels.csv").open()))
    assert [r["case_id"] for r in rows] == [c["case_id"] for c in cases]
    assert all(r["helpfulness_label"].strip() in ("", "1", "2", "3", "4", "5") for r in rows)  # empty until a person fills them in; never auto-filled


# --- the dashboard ---------------------------------------------------------------------------------------------------

def sample_spans() -> list[dict]:
    spans = miss_trace("m1", 1000.0, total=10.0) + miss_trace("m2", 1100.0, total=12.0, planner=4.0) + hit_trace("h1", 1200.0) + hit_trace("h2", 1201.0, 0.05)
    failed = miss_trace("f1", 1300.0, total=25.0, status="error")
    failed[5].update(status="error", error="OperationalError: mysql down")
    spans += failed
    spans += [span_row("m1", "evaluation", 1010.0, 1030.0, judge_calls=3)]
    return spans


def test_dashboard_summary_separates_hits_from_misses_and_computes_the_error_rate():
    m = dash.summary_metrics(sample_spans())
    assert m["requests"] == 5 and m["hits"] == 2 and m["misses"] == 3 and m["errors"] == 1 and abs(m["error_rate"] - 0.2) < 1e-9 and abs(m["hit_rate"] - 0.4) < 1e-9
    assert m["latency_hit"]["n"] == 2 and m["latency_miss"]["n"] == 2  # the failed request is not counted in the miss latency
    assert abs(m["latency_hit"]["p50_ms"] - 40.0) < 1e-6 and abs(m["latency_miss"]["p50_ms"] - 11000.0) < 1e-6


def test_dashboard_time_window_ends_at_the_newest_span_and_filters_requests():
    spans = sample_spans()
    start, end = dash.window_bounds(spans, 30)
    assert end == max(s["end_ts"] for s in spans) and dash.summary_metrics(dash.in_window(spans, start, end))["requests"] == 1
    assert dash.summary_metrics(dash.in_window(spans, *dash.window_bounds(spans, None)))["requests"] == 5
    assert dash.window_bounds([], None) == (0.0, 0.0)


def test_dashboard_stage_table_has_the_six_required_stages():
    rows = {r["Stage"]: r for r in dash.stage_table(sample_spans())}
    assert list(rows) == ["Cache lookup", "Planner", "Writer", "Reviewer", "Queue wait (total)", "Evaluation"]
    assert rows["Planner"]["Requests"] == 2 and abs(rows["Planner"]["p50 (ms)"] - 3500.0) < 1 and rows["Evaluation"]["Requests"] == 1
    assert abs(rows["Queue wait (total)"]["p50 (ms)"] - 100.0) < 1  # 30 + 20 + 30 + 20 ms


def test_dashboard_trace_index_labels_each_path():
    index = {r["trace_id"]: r for r in dash.trace_index(sample_spans())}
    assert index["h1"]["path"] == "cache_hit" and index["m1"]["path"] == "cache_miss" and index["f1"]["path"] == "failed" and index["f1"]["failing_stage"] == "writer"


def test_coordination_summary_is_computed_from_the_scores():
    evals = [{"plan_quality": {"score": 3}, "writer_helpfulness": {"score": 4, "draft": "A"}, "final_answer_helpfulness": {"score": 5, "final_answer": "A", "review_status": "approved"},
              "final_vs_draft": {"difference": 1}, "question": "q", "trace_id": "t"},
             {"plan_quality": {"score": 3}, "writer_helpfulness": {"score": 5, "draft": "B"}, "final_answer_helpfulness": {"score": 5, "final_answer": "B", "review_status": "approved"},
              "final_vs_draft": {"difference": 0}, "question": "q", "trace_id": "t2"}]
    text = " ".join(dash.coordination_summary(dash.evaluation_rows(evals), evals))
    assert "plan 3.00" in text and "unchanged in 2 requests" in text and "lowest-scoring stage is the plan" in text and "+1" in text


def write_sample_spans() -> Path:
    path = Path(tempfile.mkdtemp(dir=_TMP)) / "spans.jsonl"
    path.write_text("\n".join(json.dumps(s) for s in sample_spans()) + "\n")
    return path


def test_streamlit_pages_render_without_errors_and_show_the_required_items():
    from streamlit.testing.v1 import AppTest
    os.environ["DASHBOARD_SPANS"] = str(write_sample_spans())
    try:
        at = AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=60).run()
        assert not at.exception
        labels = {m.label: m.value for m in at.metric}
        assert labels["Requests"] == "5" and labels["Semantic-cache hit rate"] == "40.0%" and labels["Error rate"] == "20.0%"
        captions = " ".join(c.value for c in at.caption)
        assert "Data source" in captions and "Time window" in captions
        at.sidebar.radio[0].set_value("Evaluation").run()
        assert not at.exception
        at.sidebar.radio[0].set_value("Trace lookup").run()
        assert not at.exception
        at.text_input[0].set_value("f1").run()
        assert not at.exception and any("FAILED trace" in e.value and "writer" in e.value for e in at.error)
        at.text_input[0].set_value("h1").run()
        assert any("CACHE HIT" in s.value for s in at.success)
        at.text_input[0].set_value("m1").run()
        assert any("CACHE MISS" in i.value for i in at.info)
        at.text_input[0].set_value("does-not-exist").run()
        assert any("No spans found" in e.value for e in at.error)
    finally:
        os.environ.pop("DASHBOARD_SPANS", None)


def test_the_labeling_page_renders_and_does_not_show_judge_scores():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "dashboard/label_cases.py"), default_timeout=60).run()
    assert not at.exception and len(at.radio) == 1
    page = " ".join([m.value for m in at.markdown] + [c.value for c in at.caption] + [h.value for h in at.subheader])
    assert "judge" in page.lower() and "No judge score is shown" in page


def test_evaluator_since_option_accepts_epoch_and_iso_times():
    import evaluator
    assert evaluator.parse_since("1700000000") == 1700000000.0
    assert evaluator.parse_since("2026-11-15T09:00:00Z") == evaluator.parse_since("2026-11-15T09:00:00")
    assert evaluator.parse_since(None) == 0.0


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main() -> int:
    logging.disable(logging.CRITICAL)
    failed = 0
    started = time.time()
    for test in TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - report every failing test
            failed += 1
            print(f"FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed ({time.time() - started:.1f}s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
