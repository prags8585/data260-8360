#!/usr/bin/env python3
import argparse
import json
import logging
import sys
import time

from confluent_kafka import TopicPartition

from kafka_svc import config
from kafka_svc.bus import compact, decode, make_consumer, make_producer, new_correlation_id, send, setup_logging, utc_now

log = logging.getLogger("send_question")
DEFAULT_QUESTION = "Which department has the most available seats, and which course there has the most seats?"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    setup_logging()
    consumer = make_consumer(f"{config.PREFIX}_asker_{new_correlation_id()[:8]}", "send_question", offset_reset="latest")
    meta = consumer.list_topics(config.FINAL_TOPIC, timeout=10).topics[config.FINAL_TOPIC]
    consumer.assign([TopicPartition(config.FINAL_TOPIC, p, consumer.get_watermark_offsets(TopicPartition(config.FINAL_TOPIC, p), timeout=10)[1])
                     for p in meta.partitions])

    producer = make_producer("send_question")
    correlation_id = new_correlation_id()
    question = {"correlation_id": correlation_id, "question": args.question, "submitted_at": utc_now()}
    log.info("sending question to %s correlation_id=%s message=%s", config.INBOX_TOPIC, correlation_id, compact(question))
    partition, offset = send(producer, config.INBOX_TOPIC, question, key=correlation_id)
    log.info("question acknowledged by the broker partition=%d offset=%d correlation_id=%s", partition, offset, correlation_id)

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        msg = consumer.poll(1.0)
        body = decode(msg) if msg is not None and not msg.error() else None
        if body and body.get("correlation_id") == correlation_id:
            log.info("received final message from %s partition=%d offset=%d correlation_id=%s", config.FINAL_TOPIC, msg.partition(), msg.offset(), correlation_id)
            print(json.dumps(body, indent=2))
            consumer.close()
            return 0 if body.get("status") == "approved" else 2
    log.error("no final message for correlation_id=%s within %gs", correlation_id, args.timeout)
    consumer.close()
    return 1


if __name__ == "__main__":
    sys.exit(main())
