#!/usr/bin/env python3
"""HW10 Part 2: the evaluator. Reads the plan (s8360_tasks), draft (s8360_drafts) and final (s8360_final) messages and joins them by correlation_id,
then scores every complete request with the DeepEval/GEval judge (qwen3:8b via Ollama) and appends one JSON line per request to --out.

It uses its own consumer group on a fresh start and replays the topics from the beginning (nothing is committed), so it never disturbs the Planner, Writer
or Reviewer groups. A request that was already scored (its trace_id is in --out) is skipped. --once drains the topics and exits."""
import argparse
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from confluent_kafka import KafkaError

from evaluation.judge import LocalOllamaJudge
from evaluation.pipeline_eval import JoinStore, evaluate_trace
from kafka_svc import config
from kafka_svc.bus import decode, make_consumer, new_correlation_id, setup_logging
from tracing.spans import message_time

log = logging.getLogger("evaluator")
ROOT = Path(__file__).resolve().parent


def parse_since(text: str | None) -> float:
    """Epoch seconds, or an ISO time (read as UTC when it has no zone)."""
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).timestamp()


def already_scored(path: Path) -> set[str]:
    done = set()
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                done.add(json.loads(line)["trace_id"])
            except (ValueError, KeyError):
                continue
    return done


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "kafka_state/evals/evals.jsonl")
    parser.add_argument("--since", default=None, help="only evaluate requests whose plan was produced after this epoch second / ISO time")
    parser.add_argument("--once", action="store_true", help="drain the topics, evaluate what is complete, then exit")
    parser.add_argument("--idle", type=float, default=15.0, help="--once: stop after this many seconds without a new message")
    parser.add_argument("--max-seconds", type=float, default=3600.0, help="hard limit for the whole run, so a stuck judge or broker cannot hang it")
    parser.add_argument("--only", nargs="*", default=None, help="evaluate only these trace_ids")
    args = parser.parse_args()

    setup_logging()
    since = parse_since(args.since)
    stopping = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stopping.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stopping.update(flag=True))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = already_scored(args.out)
    judge = LocalOllamaJudge()
    store = JoinStore()
    # scoring one request can take minutes when the machine is loaded (3 judge calls, each up to 2 x 90 s), so the poll interval must be longer than that;
    # with Kafka's default of 300 s a slow request got the consumer evicted from its group (seen once in the HW10 re-run)
    consumer = make_consumer(f"{config.PREFIX}_evaluator_{new_correlation_id()[:8]}", "evaluator", offset_reset="earliest", extra={"max.poll.interval.ms": 1_500_000})
    consumer.subscribe([config.TASKS_TOPIC, config.DRAFTS_TOPIC, config.FINAL_TOPIC])
    log.info("evaluator ready: topics %s, judge %s, output %s, %d requests already scored", [config.TASKS_TOPIC, config.DRAFTS_TOPIC, config.FINAL_TOPIC],
             judge.get_model_name(), args.out, len(done))
    started, last_message, evaluated = time.time(), time.time(), 0
    try:
        while not stopping["flag"] and time.time() - started < args.max_seconds:
            msg = consumer.poll(1.0)
            if msg is None:
                if args.once and time.time() - last_message > args.idle:
                    break
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    log.warning("consumer error: %s", msg.error())
                continue
            last_message = time.time()
            produced = message_time(msg)
            if produced is not None and produced < since:
                continue
            kind = msg.topic().removeprefix(f"{config.PREFIX}_")
            cid = store.add(kind, decode(msg), produced, {"topic": msg.topic(), "partition": msg.partition(), "offset": msg.offset(), "timestamp_ms": None if produced is None else int(produced * 1000)})
            if cid is None:
                log.warning("skipped a message from %s offset=%d (malformed, test traffic, or without a correlation_id)", msg.topic(), msg.offset())
                continue
            if store.complete(cid) and cid not in done and (args.only is None or cid in args.only):
                log.info("plan, draft and final joined for correlation_id=%s; judging", cid)
                meta = {"plan": store.plans[cid]["meta"], "draft": store.drafts[cid]["meta"], "final": store.finals[cid]["meta"]}
                record = evaluate_trace(cid, store.plans[cid]["body"], store.drafts[cid]["body"], store.finals[cid]["body"], judge, meta=meta)
                with open(args.out, "a") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                done.add(cid)
                evaluated += 1
                log.info("scored correlation_id=%s plan=%s writer=%s final=%s in %.1fs errors=%s", cid, record["plan_quality"]["score"],
                         record["writer_helpfulness"]["score"], record["final_answer_helpfulness"]["score"], record["duration_ms"] / 1000, record["errors"] or "none")
    finally:
        consumer.close()
    log.info("evaluator finished: %d scored, %d malformed or skipped, %d incomplete joins", evaluated, store.skipped, len(store.incomplete()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
