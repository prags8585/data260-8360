#!/usr/bin/env python3
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports/hw08/raw"


def load(name):
    return json.loads((RAW / name).read_text())


def ts(line):
    return datetime.strptime(line.split(" ", 1)[0], "%Y-%m-%dT%H:%M:%S.%fZ")


def journey():
    log = (RAW / "logs/part2_send_question.log").read_text()
    cid = re.search(r"correlation_id=(\S+)", log).group(1)
    lines = [ln for f in ("part2_send_question", "part2_planner", "part2_writer", "part2_reviewer") for ln in (RAW / f"logs/{f}.log").read_text().splitlines() if cid in ln]
    pick = lambda key: ts(next(ln for ln in lines if key in ln))  # noqa: E731
    t = {"sent": pick("sending question"), "planner_in": pick("received question"), "plan_out": pick("sending plan"), "writer_in": pick("received task"),
         "draft_out": pick("sending draft"), "reviewer_in": pick("received draft"), "final_out": pick("sending final"), "client_in": pick("received final message")}
    gap = lambda a, b: round((t[b] - t[a]).total_seconds(), 2)  # noqa: E731
    return cid, [("question sent -> Planner receives", gap("sent", "planner_in")), ("Planner (qwen3:8b plan)", gap("planner_in", "plan_out")),
                 ("tasks topic -> Writer receives", gap("plan_out", "writer_in")), ("Writer (facts + qwen3:8b draft)", gap("writer_in", "draft_out")),
                 ("drafts topic -> Reviewer receives", gap("draft_out", "reviewer_in")), ("Reviewer (deterministic checks)", gap("reviewer_in", "final_out")),
                 ("final topic -> client receives", gap("final_out", "client_in")), ("end to end", gap("sent", "client_in"))]


def main() -> None:
    dup, death, poison, order = (load(f"failure_{n}.json") for n in ("duplicate", "death", "poison", "ordering"))
    lag = lambda entry: sum(r["lag"] or 0 for r in entry["offsets_after_kill"]["rows"])  # noqa: E731
    dead = poison["after"]["dead_letter_records"][0]
    ob, oa = order["before"]["analysis"], order["after"]["analysis"]
    cid, stages = journey()
    out = ["# METRICS - DATA-260 Homework 8", "",
           "Numbers come from the files in `reports/hw08/raw/` (one run each; unkeyed partitioning is random, so the exact ordering numbers differ from run to run).", "",
           "## Configuration", "",
           "| Value | Setting |", "|---|---|",
           "| SID4 / PORT_BASE / PREFIX / SEED / VERIFY_SEED | 8360 / 8260 / s8360 / 8360 / 268360 |",
           "| DOMAIN_ID / primary entity | 0 (Campus Course Catalogue and Enrolment) / Course |",
           "| Broker | Apache Kafka 3.8.0, KRaft, one broker, replication factor 1 |",
           "| Client library | confluent-kafka 2.16.1 (acks=all, idempotent producer, manual offset commit) |",
           "| Part 2 model | qwen3:8b via Ollama, temperature 0, seed 8360 (Parts 1 and 3 use no model) |", ""]
    out += ["", f"## Part 2 - one message journey (correlation_id {cid})", "", "| Stage | Seconds |", "|---|---|"]
    out += [f"| {name} | {sec} |" for name, sec in stages]
    out += ["", "## Part 3 - failure behaviour (before / after)", "",
            "| Failure scenario | Before fix | After fix |", "|---|---|---|",
            f"| Duplicate delivery | replayed correlation_id -> {dup['before']['drafts_published']} drafts published (side effect twice) | {dup['after']['drafts_published']} draft; replay logged as DUPLICATE and skipped |",
            f"| Consumer killed mid-work | offset auto-committed before the work finished: lag after kill {lag(death['before'])}, redelivered after restart: {death['before']['redelivered_after_restart']}, drafts {death['before']['drafts_final']} (message lost) | offset committed after the draft: lag after kill {lag(death['after'])}, redelivered: {death['after']['redelivered_after_restart']}, drafts {death['after']['drafts_final']} |",
            f"| Poison message | writer exits with code {poison['before']['first_run_exit_code']} on it, again after restart ({poison['before']['second_run_exit_code']}); later message processed: {poison['before']['good_message_processed']}; lag {sum(r['lag'] for r in poison['before']['offsets']['rows'])} | {dead['attempts']} attempts, then dead-letter record at offset {dead['source_offset']}; later message processed: {poison['after']['good_message_processed']}; lag {sum(r['lag'] for r in poison['after']['offsets']['rows'])} |",
            f"| Two partitions / two consumers | no key: {ob['total_inversions']} order inversions, {ob['entities_in_order']}/{len(ob['entities'])} entities in order, {ob['entities_in_one_partition']}/{len(ob['entities'])} in one partition | key = course code: {oa['total_inversions']} inversions, {oa['entities_in_order']}/{len(oa['entities'])} entities in order, {oa['entities_in_one_partition']}/{len(oa['entities'])} in one partition |",
            "", "## Part 3 - ordering detail (VERIFY_SEED 268360, 20 messages)", "",
            "| Entity | Messages | No key: partitions | No key: processed seq order | Key: partitions | Key: processed seq order |", "|---|---|---|---|---|---|"]
    for entity, info in ob["entities"].items():
        k = oa["entities"][entity]
        out.append(f"| {entity} | {info['messages']} | {info['partitions']} | {info['processed_seqs']} | {k['partitions']} | {k['processed_seqs']} |")
    out += ["", "## Checks", "", "`python tests_hw8.py` (25 offline tests) and `python verify_hw08.py` (live smoke test, writes `verification.json`).", ""]
    (ROOT / "reports/hw08/METRICS.md").write_text("\n".join(out))
    print("METRICS lines:", len(out))


if __name__ == "__main__":
    main()
