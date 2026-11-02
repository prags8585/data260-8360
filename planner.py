#!/usr/bin/env python3
import argparse
import logging
import signal

from kafka_svc import config
from kafka_svc.brains import make_model, plan_llm, plan_rule
from kafka_svc.bus import compact, dead_letter, decode, make_consumer, make_producer, send, setup_logging, utc_now

log = logging.getLogger("planner")


def handle(msg, producer, model) -> None:
    body = decode(msg)
    if body is None or not isinstance(body.get("correlation_id"), str) or not isinstance(body.get("question"), str):
        raise ValueError("inbox message needs a correlation_id and a question")
    cid = body["correlation_id"]
    log.info("received question from %s partition=%d offset=%d correlation_id=%s message=%s",
             msg.topic(), msg.partition(), msg.offset(), cid, compact(body))
    plan, source = plan_llm(model, body["question"]) if model else (plan_rule(body["question"]), "rule")
    task = {"correlation_id": cid, "question": body["question"], "plan": plan, "plan_source": source, "planned_at": utc_now()}
    log.info("sending plan to %s correlation_id=%s message=%s", config.TASKS_TOPIC, cid, compact(task))
    partition, offset = send(producer, config.TASKS_TOPIC, task, key=cid)
    log.info("plan acknowledged by the broker partition=%d offset=%d correlation_id=%s", partition, offset, cid)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brain", choices=["llm", "rule"], default="llm")
    parser.add_argument("--group", default=config.PLANNER_GROUP)
    args = parser.parse_args()

    setup_logging()
    stopping = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stopping.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stopping.update(flag=True))
    model = make_model(json_mode=True) if args.brain == "llm" else None
    producer = make_producer("planner")
    consumer = make_consumer(args.group, "planner")
    consumer.subscribe([config.INBOX_TOPIC], on_assign=lambda _c, ps: log.info(
        "Planner ready, reading %s (group %s, partitions %s), model %s",
        config.INBOX_TOPIC, args.group, [p.partition for p in ps], config.MODEL if model else "none (rule brain)"))
    try:
        while not stopping["flag"]:
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            try:
                handle(msg, producer, model)
            except Exception as exc:
                log.exception("bad inbox message, moving it to %s", config.DEAD_LETTER_TOPIC)
                dead_letter(producer, msg, f"{type(exc).__name__}: {exc}", 1)
            consumer.commit(message=msg, asynchronous=False)
    finally:
        consumer.close()
        log.info("planner stopped")


if __name__ == "__main__":
    main()
