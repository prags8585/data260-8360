#!/usr/bin/env python3
import argparse
import json
import logging
import signal
import time
from pathlib import Path

from kafka_svc import config
from kafka_svc.brains import make_model, write_draft
from kafka_svc.bus import compact, dead_letter, decode, make_consumer, make_producer, send, setup_logging, utc_now
from kafka_svc.idempotency import ProcessedStore

log = logging.getLogger("writer")
BACKOFF_SECONDS = 0.5


def produce_draft(msg, body: dict, args, model, producer) -> None:
    """The side effect: one draft on the drafts topic (after the simulated work time, if the task asks for any)."""
    if not isinstance(body.get("plan"), list):
        raise TypeError("task has no plan list")
    time.sleep(body.get("work_ms", 0) / 1000)
    draft, facts = write_draft(args.brain, model, body["question"], body["plan"])
    out = {"correlation_id": body["correlation_id"], "question": body["question"], "plan": body["plan"], "draft": draft,
           "facts": facts, "written_by": args.id, "written_at": utc_now()}
    if body.get("test"):
        out["test"] = body["test"]
    log.info("sending draft to %s correlation_id=%s message=%s", config.DRAFTS_TOPIC, body["correlation_id"], compact(out))
    partition, offset = send(producer, config.DRAFTS_TOPIC, out, key=body["correlation_id"])
    log.info("draft acknowledged by the broker partition=%d offset=%d correlation_id=%s", partition, offset, body["correlation_id"])


def handle(msg, args, model, producer, consumer, processed: ProcessedStore | None, trace: Path | None) -> None:
    where = f"{msg.topic()} partition={msg.partition()} offset={msg.offset()}"
    body = decode(msg)
    cid = body.get("correlation_id") if body else (msg.key().decode("utf-8", "replace") if msg.key() else None)
    log.info("received task from %s correlation_id=%s", where, cid)
    started = utc_now()

    if processed is not None and cid and processed.seen(cid):
        log.warning("DUPLICATE correlation_id=%s already processed, skipping the side effect", cid)
        finish(msg, args, consumer)
        return

    attempts = 0
    while True:
        attempts += 1
        try:
            if body is None:
                raise ValueError("task is not valid JSON")
            log.info("processing correlation_id=%s attempt %d/%d", cid, attempts, args.max_attempts)
            produce_draft(msg, body, args, model, producer)
            if processed is not None:
                processed.mark(cid, args.id)
            break
        except Exception as exc:
            if not args.dlq:
                raise
            log.warning("attempt %d/%d failed for %s offset=%d: %s: %s", attempts, args.max_attempts, msg.topic(), msg.offset(), type(exc).__name__, exc)
            if attempts >= args.max_attempts:
                partition, offset = dead_letter(producer, msg, f"{type(exc).__name__}: {exc}", attempts)
                log.error("gave up after %d attempts, moved %s offset=%d to %s partition=%d offset=%d",
                          attempts, msg.topic(), msg.offset(), config.DEAD_LETTER_TOPIC, partition, offset)
                break
            time.sleep(BACKOFF_SECONDS * 2 ** (attempts - 1))

    if trace and body:
        with open(trace, "a") as handle_file:
            handle_file.write(json.dumps({"writer": args.id, "partition": msg.partition(), "offset": msg.offset(), "correlation_id": cid,
                                          "entity": body.get("entity"), "seq": body.get("seq"), "started_at": started, "finished_at": utc_now()}) + "\n")
    finish(msg, args, consumer)


def finish(msg, args, consumer) -> None:
    if args.auto_commit:
        return
    consumer.commit(message=msg, asynchronous=False)
    log.info("committed offset %d on %s partition=%d", msg.offset() + 1, msg.topic(), msg.partition())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", default="writer-1")
    parser.add_argument("--brain", choices=["llm", "rule"], default="llm")
    parser.add_argument("--group", default=config.WRITER_GROUP)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--no-idempotency", action="store_true", help="process every delivery, even a replay of the same correlation_id")
    parser.add_argument("--auto-commit", action="store_true", help="let the client commit offsets in the background (before processing is finished)")
    parser.add_argument("--no-dlq", action="store_true", help="no retries and no dead-letter topic: a bad message raises")
    parser.add_argument("--naive", action="store_true", help="all three switches above")
    parser.add_argument("--state-db", default="kafka_state/writer_processed.sqlite")
    parser.add_argument("--trace-file", type=Path, default=None)
    args = parser.parse_args()
    if args.naive:
        args.no_idempotency = args.auto_commit = args.no_dlq = True
    args.dlq = not args.no_dlq
    if args.no_dlq:
        args.max_attempts = 1

    setup_logging()
    stopping = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stopping.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stopping.update(flag=True))
    model = make_model() if args.brain == "llm" else None
    producer = make_producer(args.id)
    consumer = make_consumer(args.group, args.id, auto_commit=args.auto_commit)
    processed = None if args.no_idempotency else ProcessedStore(args.state_db)
    log.info("%s starting: brain=%s idempotency=%s commit=%s retries=%d dead_letter=%s", args.id, args.brain,
             "on" if processed else "off", "auto (before processing ends)" if args.auto_commit else "after processing", args.max_attempts,
             "on" if args.dlq else "off")
    consumer.subscribe([config.TASKS_TOPIC],
                       on_assign=lambda _c, ps: log.info("Writer %s ready, reading %s (group %s), assigned partitions %s",
                                                         args.id, config.TASKS_TOPIC, args.group, sorted(p.partition for p in ps)),
                       on_revoke=lambda _c, ps: log.info("partitions revoked %s", sorted(p.partition for p in ps)))
    try:
        while not stopping["flag"]:
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            handle(msg, args, model, producer, consumer, processed, args.trace_file)
    finally:
        consumer.close()
        log.info("%s stopped", args.id)


if __name__ == "__main__":
    main()
