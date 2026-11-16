"""HW10 Part 1: the Streamlit operations dashboard for the s8360 system (HW8 Kafka pipeline + HW9 semantic cache).

    streamlit run dashboard/app.py

Three pages: Summary, Evaluation and Trace lookup. The numbers come from the structured spans the services write (tracing/spans.py) and from the
evaluation files of Parts 2 and 3; every page states its data source and time window."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard import data  # noqa: E402
from tracing.store import load_spans  # noqa: E402

PAGES = ["Summary", "Evaluation", "Trace lookup"]
PATH_COLORS = alt.Scale(domain=["cache_hit", "cache_miss", "failed"], range=["#2ca02c", "#1f77b4", "#d62728"])


@st.cache_data(show_spinner=False)
def read_spans(path: str, mtime: float) -> list[dict]:
    """Parsing the span file is the expensive part; the file's modification time is part of the cache key, so new spans show up on the next rerun."""
    return load_spans(path)


@st.cache_data(show_spinner=False)
def read_file(path: str, mtime: float):
    p = Path(path)
    return data.load_jsonl(p) if p.suffix == ".jsonl" else data.load_json(p)


@st.cache_resource(show_spinner=False)
def redis_cache():
    """One shared connection to the Redis semantic cache for the whole app (a resource, not data)."""
    from cache_svc.semantic_cache import SemanticCache
    return SemanticCache()


def mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


def spans() -> tuple[list[dict], Path]:
    path = data.spans_path()
    return read_spans(str(path), mtime(path)), path


def fmt(value, unit="ms", digits=0):
    return "n/a" if value is None else f"{value:.{digits}f} {unit}"


def shown(path: Path) -> str:
    return str(path.relative_to(data.ROOT)) if path.is_relative_to(data.ROOT) else str(path)


def summary_page() -> None:
    st.header("Summary")
    all_spans, path = spans()
    if not all_spans:
        st.warning(f"No spans found in {path}. Send some requests through the ingress (POST /ask) first.")
        return
    choice = st.selectbox("Time window", list(data.WINDOWS), help="The window ends at the newest span in the file and goes back from there.")
    start, end = data.window_bounds(all_spans, data.WINDOWS[choice])
    window = data.in_window(all_spans, start, end)
    m = data.summary_metrics(window)
    st.caption(f"Data source: `{shown(path)}` (the `request` spans written by the ingress). Time window: {data.utc(start)} to {data.utc(end)}.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Requests", m["requests"], help="Count of `request` spans (one per call to POST /ask) in the window.")
    c2.metric("Semantic-cache hit rate", "n/a" if m["hit_rate"] is None else f"{m['hit_rate']:.1%}", help="Cache hits divided by requests in the window.")
    c3.metric("Error rate", "n/a" if m["error_rate"] is None else f"{m['error_rate']:.1%}",
              help="Requests whose `request` span has status error (the pipeline did not answer in time) divided by requests.")
    c4.metric("Rejected by the Reviewer", m["rejected"], help="Requests that went through the pipeline and got no answer because the Reviewer rejected the draft (not counted as errors).")
    where = f"`{shown(path)}`, window {data.utc(start)} to {data.utc(end)}"
    st.caption(f"**Requests** ({m['requests']}): count of `request` spans, source {where}.  \n"
               f"**Cache hit rate** ({m['hits']} hits, {m['misses']} misses): hits / requests, `request` spans with path = cache_hit or cache_miss, source {where}.  \n"
               f"**Error rate** ({m['errors']} of {m['requests']}): `request` spans with status error / requests, source {where}.  \n"
               f"**Rejected by the Reviewer** ({m['rejected']}): `request` spans with review_status = rejected, source {where}.")

    st.subheader("Cache hits and cache misses are separate")
    left, right = st.columns(2)
    with left:
        st.markdown("**Cache hit** (answered from Redis, no agent run)")
        h = m["latency_hit"]
        st.metric("Hits", h["n"])
        st.write(f"end-to-end latency: p50 **{fmt(h['p50_ms'], digits=1)}**, p95 **{fmt(h['p95_ms'], digits=1)}**, mean {fmt(h['mean_ms'], digits=1)}")
    with right:
        st.markdown("**Cache miss** (Planner, Writer, Reviewer ran)")
        ms = m["latency_miss"]
        st.metric("Misses answered", ms["n"])
        st.write(f"end-to-end latency: p50 **{fmt(ms['p50_ms'])}**, p95 **{fmt(ms['p95_ms'])}**, mean {fmt(ms['mean_ms'])}")
    st.caption(f"Latency source: `request` span duration (cache lookup to answer returned), per path. Window: {data.utc(start)} to {data.utc(end)}.")

    st.subheader("Where the time goes on a cache miss")
    st.dataframe(pd.DataFrame(data.stage_table(window)), hide_index=True, width="stretch")
    st.caption("p50 and p95 per stage over the answered cache-miss requests in the window. Queue wait is the four Kafka topic waits of a request added up. "
               "Evaluation runs after the answer, in the evaluator process.")

    traces = pd.DataFrame(data.trace_index(window))
    if len(traces):
        traces = traces[traces["has_request_span"]].copy()
        traces["minute"] = pd.to_datetime(traces["start_ts"], unit="s").dt.floor("min")
        chart = alt.Chart(traces).mark_bar().encode(x=alt.X("minute:T", title="time (UTC)"), y=alt.Y("count()", title="requests"), color=alt.Color("path:N", title="path", scale=PATH_COLORS))
        st.altair_chart(chart, width="stretch")
        st.caption("Requests per minute by path (green = cache hit, blue = cache miss, red = failed). Same window and source.")
    try:
        cache = redis_cache()
        st.caption(f"Live Redis semantic cache right now: {cache.size()} entries (this one number is read from Redis, not from the span file).")
    except Exception:
        st.caption("Live Redis cache size is not available (Redis is not reachable).")


def evaluation_page() -> None:
    st.header("Evaluation")
    evals_path = data.RAW / "part2_evals.jsonl"
    evals = read_file(str(evals_path), mtime(evals_path)) or []
    st.subheader("Part 2 - Planner, Writer and Reviewer scored by the judge")
    st.caption("Source: `reports/hw10/raw/part2_evals.jsonl` (one line per request, written by evaluator.py). Judge: DeepEval GEval on qwen3:8b via Ollama, temperature 0, seed 8360, scale 1-5.")
    if not evals:
        st.info("No Part 2 results yet. Run the test questions, then `python evaluator.py --once`.")
    else:
        rows = data.evaluation_rows(evals)
        frame = pd.DataFrame(rows)
        st.dataframe(frame.drop(columns=["trace_id"]), hide_index=True, width="stretch")
        stages = ["Plan quality", "Writer helpfulness", "Final answer helpfulness"]
        by_stage = frame[stages].mean().rename("mean score").reset_index().rename(columns={"index": "stage"})
        st.markdown("**Mean score by pipeline stage**")
        st.altair_chart(alt.Chart(by_stage).mark_bar().encode(x=alt.X("stage:N", sort=None, title=None), y=alt.Y("mean score:Q", scale=alt.Scale(domain=[0, 5])),
                                                              color=alt.Color("stage:N", legend=None)), width="stretch")
        long = frame.melt(id_vars=["case", "question"], value_vars=stages, var_name="stage", value_name="score")
        st.markdown("**Scores by case and stage**")
        st.altair_chart(alt.Chart(long).mark_rect().encode(x=alt.X("stage:N", sort=None, title=None), y=alt.Y("case:N", title=None),
                                                           color=alt.Color("score:Q", scale=alt.Scale(domain=[1, 5], scheme="redyellowgreen")),
                                                           tooltip=["question", "stage", "score"]), width="stretch")
        with st.expander("Judge reasons and the Final-vs-Draft comparison per case"):
            for r, e in zip(rows, evals):
                fvd = e["final_vs_draft"]
                st.markdown(f"**{r['case']} - {r['question']}**  \n`trace_id` {r['trace_id']}")
                st.write(f"Plan {r['Plan quality']}: {e['plan_quality']['reason']}")
                st.write(f"Writer draft {r['Writer helpfulness']}: {e['writer_helpfulness']['reason']}")
                st.write(f"Final answer {r['Final answer helpfulness']}: {e['final_answer_helpfulness']['reason']}")
                st.write(f"Final vs draft: {fvd['draft_score']} -> {fvd['final_score']} (difference {fvd['difference']}). {fvd['interpretation']}")
        st.markdown("**What the scores suggest about Planner, Writer and Reviewer coordination**")
        for line in data.coordination_summary(rows, evals):
            st.write("- " + line)

    st.subheader("Part 3 - is the judge reliable? (20 drafts, human labels)")
    validation_path = data.RAW / "judge_validation.json"
    validation = read_file(str(validation_path), mtime(validation_path))
    st.caption("Source: `reports/hw10/raw/judge_validation.json`, computed from `eval_cases.json`, `human_labels.csv` and three judge runs.")
    if not validation:
        st.info("Judge validation has not been run yet: it needs `human_labels.csv` (hand-assigned labels) first.")
        return
    a, b, c, d = st.columns(4)
    a.metric("Spearman correlation", f"{validation['spearman']['rho']:.3f}", help=f"human vs judge (run 1), p = {validation['spearman']['p_value']:.4f}")
    b.metric("Mean absolute difference", f"{validation['mean_absolute_difference']:.2f}", help="mean |human - judge| on the 1-5 scale")
    c.metric("Exact agreement", f"{validation['exact_agreement']:.0%}", help="share of drafts where judge = human")
    d.metric("Within 1 point", f"{validation['within_one']:.0%}")
    rep = validation["repeatability"]
    st.markdown(f"**Repeatability ({rep['runs']} runs, same inputs and settings):** {rep['cases_with_any_change']} of {validation['n']} drafts changed score between runs; "
                f"mean absolute change {rep['mean_abs_change']:.3f}, maximum {rep['max_abs_change']}.")
    cases = pd.DataFrame(validation["cases"])
    scatter = alt.Chart(cases).mark_circle(size=120).encode(x=alt.X("human:Q", title="human label", scale=alt.Scale(domain=[0.5, 5.5])),
                                                           y=alt.Y("judge_run1:Q", title="judge score (run 1)", scale=alt.Scale(domain=[0.5, 5.5])),
                                                           tooltip=["case_id", "human", "judge_run1", "judge_run2", "judge_run3"])
    st.altair_chart(scatter, width="stretch")
    st.write(validation.get("verdict", ""))
    with st.expander("Per-case data (human label and the three judge runs)"):
        st.dataframe(cases.drop(columns=[c for c in ("judge_reason_run1",) if c in cases]), hide_index=True, width="stretch")


def trace_page() -> None:
    st.header("Trace lookup")
    all_spans, path = spans()
    st.caption(f"Data source: `{shown(path)}`. trace_id is the HW8 correlation_id.")
    examples = data.example_traces()
    index = data.trace_index(all_spans)
    labels = {v["trace_id"]: f"{k.replace('_', ' ')} example" for k, v in examples.items()}
    quick = st.selectbox("Example traces (one cache hit, one cache miss, one failed)", [""] + list(labels), format_func=lambda t: "choose one" if not t else f"{labels[t]}: {t}")
    typed = st.text_input("trace_id", value=quick, placeholder="paste a trace_id")
    if not typed.strip():
        recent = pd.DataFrame(index[:15])
        if len(recent):
            st.markdown("Recent traces")
            st.dataframe(recent[["trace_id", "start", "path", "total_ms", "failing_stage"]], hide_index=True, width="stretch")
        return
    typed = typed.strip()
    sp = data.trace_spans(all_spans, typed)
    if not sp:
        st.error(f"No spans found for trace_id {typed!r}.")
        return
    info = next(r for r in index if r["trace_id"] == typed)
    if info["path"] == "cache_hit":
        st.success(f"CACHE HIT path: answered from the semantic cache in {info['total_ms']:.0f} ms; no Kafka stage ran.")
    elif info["path"] == "failed":
        bad = data.failing_span(sp)
        st.error(f"FAILED trace: first failing stage = {info['failing_stage']}. Error: {bad['error'] if bad else 'n/a'}")
    else:
        st.info(f"CACHE MISS path: the request went through the Kafka pipeline; {info['total_ms']:.0f} ms end to end." if info["total_ms"] else "CACHE MISS path.")
    t0 = sp[0]["start_ts"]
    st.dataframe(pd.DataFrame([{"stage": s["stage"], "start": s["start"], "end": s["end"], "duration (ms)": s["duration_ms"], "status": s["status"],
                                "error": s["error"] or "", "details": data.span_notes(s)} for s in sp]), hide_index=True, width="stretch", height=40 + 35 * len(sp),
                 column_config={"error": st.column_config.TextColumn(width="medium"), "details": st.column_config.TextColumn(width="large")})
    gantt = pd.DataFrame([{"stage": s["stage"], "from (ms)": (s["start_ts"] - t0) * 1000, "to (ms)": (s["end_ts"] - t0) * 1000, "status": s["status"]} for s in sp])
    st.altair_chart(alt.Chart(gantt).mark_bar().encode(y=alt.Y("stage:N", sort=[s["stage"] for s in sp], title=None), x=alt.X("from (ms):Q", title="ms since the request started"),
                                                       x2="to (ms):Q", color=alt.Color("status:N", scale=alt.Scale(domain=["ok", "error"], range=["#1f77b4", "#d62728"]))),
                    width="stretch")
    for s in sp:
        if s["status"] == "error":
            st.error(f"{s['stage']}: {s['error']}")


def main() -> None:
    st.set_page_config(page_title="s8360 operations dashboard", layout="wide")
    st.sidebar.title("s8360 operations")
    st.sidebar.caption("HW8 Kafka pipeline + HW9 semantic cache")
    page = st.sidebar.radio("Page", PAGES, key="page")
    {"Summary": summary_page, "Evaluation": evaluation_page, "Trace lookup": trace_page}[page]()


main()
