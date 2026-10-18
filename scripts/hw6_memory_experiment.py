#!/usr/bin/env python3

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports/hw06/raw"
BASE = "http://localhost:8260"

SETTINGS = {
    "N4": {"short_term_n": 4, "policy": "none"},
    "N12": {"short_term_n": 12, "policy": "none"},
    "N30": {"short_term_n": 30, "policy": "none"},
    "compress_N12": {"short_term_n": 12, "policy": "compress"},
}


def post_chat(user_id: str, session_id: str, message: str, cfg: dict) -> dict:
    start = time.perf_counter()
    r = requests.post(f"{BASE}/api/chat", timeout=300, json={
        "user_id": user_id, "session_id": session_id, "message": message, **cfg})
    r.raise_for_status()
    body = r.json()
    body["client_latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
    return body


def score_probe(reply: str, probe: dict, unknown_phrases: list[str]) -> tuple[int, float, list[bool]]:
    text = reply.lower()
    hits = [any(alt.lower() in text for alt in element) for element in probe["expected"]]
    f = sum(hits) / len(hits)
    if f == 1.0:
        return 5, f, hits
    if f >= 0.5:
        return 4, f, hits
    if f > 0:
        return 3, f, hits
    if any(p in text for p in unknown_phrases):
        return 2, f, hits
    return 1, f, hits


def run_setting(tag: str, cfg: dict, messages: list[str], probes: dict) -> tuple[list[dict], list[dict]]:
    user_id = f"exp-{tag}-{int(time.time())}"
    session_id = f"{tag}-session"
    turns, probe_rows = [], []
    print(f"\n=== setting {tag}  {cfg}  user={user_id} ===", flush=True)
    for i, message in enumerate(messages, 1):
        body = post_chat(user_id, session_id, message, cfg)
        u = body["usage"]
        row = {
            "setting": tag, "short_term_n": cfg["short_term_n"], "policy": cfg["policy"], "turn": i,
            "prompt_tokens": u["prompt_tokens"], "completion_tokens": u["completion_tokens"],
            "primer_tokens": u["components"]["system_primer"], "long_term_tokens": u["components"]["long_term_summary"],
            "window_tokens": u["components"]["short_term_window"], "episodic_tokens": u["components"]["episodic_facts"],
            "current_tokens": u["components"]["current_message"],
            "overhead_prompt_tokens": u["overhead_prompt_tokens"], "overhead_completion_tokens": u["overhead_completion_tokens"],
            "latency_ms": u["latency_ms"], "model_latency_ms": u["model_latency_ms"],
            "window_messages": body["used"]["short_term_count"], "episodes_retrieved": len(body["used"]["episodic_facts"]),
            "summary_written": int(body["memory_updates"]["session_summary_written"]),
        }
        turns.append(row)
        print(f"  turn {i:2d}  prompt={row['prompt_tokens']:4d}  window={row['window_tokens']:4d}  "
              f"latency={row['latency_ms']:8.1f} ms", flush=True)

    for probe in probes["probes"]:
        body = post_chat(user_id, session_id, probe["question"], cfg)
        score, f, hits = score_probe(body["reply"], probe, probes["unknown_phrases"])
        probe_rows.append({
            "setting": tag, "probe_id": probe["id"], "question": probe["question"], "reply": body["reply"],
            "elements_hit": hits, "fraction": round(f, 2), "score": score,
            "prompt_tokens": body["usage"]["prompt_tokens"], "episodic_facts": [e["fact"] for e in body["used"]["episodic_facts"]],
        })
        print(f"  probe {probe['id']:<20} score={score}  reply={body['reply'][:90]!r}", flush=True)
    return turns, probe_rows


def summarise(tag: str, turns: list[dict], probes: list[dict]) -> dict:
    return {
        "setting": tag,
        "mean_prompt_tokens_per_turn": round(statistics.mean(t["prompt_tokens"] for t in turns), 1),
        "mean_completion_tokens_per_turn": round(statistics.mean(t["completion_tokens"] for t in turns), 1),
        "mean_overhead_prompt_tokens_per_turn": round(statistics.mean(t["overhead_prompt_tokens"] for t in turns), 1),
        "mean_overhead_completion_tokens_per_turn": round(statistics.mean(t["overhead_completion_tokens"] for t in turns), 1),
        "mean_window_tokens_per_turn": round(statistics.mean(t["window_tokens"] for t in turns), 1),
        "mean_latency_ms": round(statistics.mean(t["latency_ms"] for t in turns), 1),
        "mean_probe_quality": round(statistics.mean(p["score"] for p in probes), 2),
        "probe_scores": {p["probe_id"]: p["score"] for p in probes},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--settings", default="N4,N12,N30,compress_N12")
    args = ap.parse_args()
    messages = yaml.safe_load((ROOT / "memory_conversation.yaml").read_text())["messages"]
    probes = yaml.safe_load((ROOT / "memory_probes.yaml").read_text())
    assert len(messages) == 30 and len(probes["probes"]) == 5
    RAW.mkdir(parents=True, exist_ok=True)

    print(f"=== {time.strftime('%Y-%m-%d %H:%M:%S %Z')} ===  30-message conversation, 5 probes, backend {BASE}", flush=True)
    post_chat("exp-warmup", "warmup", "Hello there.", {"short_term_n": 4, "policy": "none"})   # uncounted warm-up

    all_turns, all_probes, summary = [], [], []
    for tag in args.settings.split(","):
        turns, probe_rows = run_setting(tag, SETTINGS[tag], messages, probes)
        all_turns += turns
        all_probes += probe_rows
        summary.append(summarise(tag, turns, probe_rows))
        s = summary[-1]
        print(f"  -> {tag}: mean prompt {s['mean_prompt_tokens_per_turn']} tok/turn, mean latency "
              f"{s['mean_latency_ms']} ms, probe quality {s['mean_probe_quality']}", flush=True)

    with open(RAW / "short_term_sweep_turns.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_turns[0]))
        w.writeheader()
        w.writerows(all_turns)
    (RAW / "short_term_sweep_turns.json").write_text(json.dumps(all_turns, indent=2))
    (RAW / "memory_probes_scoring.json").write_text(json.dumps(all_probes, indent=2))
    (RAW / "memory_settings_summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\n{'Setting':<14}{'Prompt tok/turn':<17}{'Latency ms':<12}{'Probe quality'}")
    for s in summary:
        print(f"{s['setting']:<14}{s['mean_prompt_tokens_per_turn']:<17}{s['mean_latency_ms']:<12}{s['mean_probe_quality']}")
    print(f"saved -> {RAW}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
