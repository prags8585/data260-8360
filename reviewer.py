#!/usr/bin/env python3
import argparse
import logging
import signal

from kafka_svc import config
from kafka_svc.brains import review_draft
from kafka_svc.bus import compact, dead_letter, decode, make_consumer, make_producer, send, setup_logging, utc_now

log = logging.getLogger("reviewer")


def handle(msg, producer) -> None:
    body = decode(msg)
    if body is None or not isinstance(body.get("correlation_id"), str) or not isinstance(body.get("draft"), str):
        raise ValueError("draft message needs a correlation_id and a draft")
    cid = body["correlation_id"]
    if body.get("test"):
        log.info("skipping %s test draft correlation_id=%s", body["test"], cid)
        return
    log.info("received draft from %s partition=%d offset=%d correlation_id=%s message=%s",
             msg.topic(), msg.partition(), msg.offset(), cid, compact(body))
    review = review_draft(body["question"], body["draft"], body["facts"])
    final = {
        "correlation_id": cid,
        "status": "approved" if review["approved"] else "rejected",
        "answer": body["draft"] if review["approved"] else None,
        "question": body["question"],
        "review": review["checks"],
        "reviewed_at": utc_now(),
    }
    log.info("review %s correlation_id=%s checks=%s", final["status"], cid, compact(review["checks"]))
    log.info("sending final message to %s correlation_id=%s message=%s", config.FINAL_TOPIC, cid, compact(final))
    partition, offset = send(producer, config.FINAL_TOPIC, final, key=cid)
    log.info("final message acknowledged by the broker partition=%d offset=%d correlation_id=%s", partition, offset, cid)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", default=config.REVIEWER_GROUP)
    args = parser.parse_args()

    setup_logging()
    stopping = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stopping.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stopping.update(flag=True))
    producer = make_producer("reviewer")
    consumer = make_consumer(args.group, "reviewer")
    consumer.subscribe([config.DRAFTS_TOPIC], on_assign=lambda _c, ps: log.info(
        "Reviewer ready, reading %s (group %s, partitions %s)", config.DRAFTS_TOPIC, args.group, [p.partition for p in ps]))
    try:
        while not stopping["flag"]:
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            try:
                handle(msg, producer)
            except Exception as exc:
                log.exception("bad draft message, moving it to %s", config.DEAD_LETTER_TOPIC)
                dead_letter(producer, msg, f"{type(exc).__name__}: {exc}", 1)
            consumer.commit(message=msg, asynchronous=False)
    finally:
        consumer.close()
        log.info("reviewer stopped")


if __name__ == "__main__":
    main()
