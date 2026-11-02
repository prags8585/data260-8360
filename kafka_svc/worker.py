import logging
import signal

from kafka_svc import config
from kafka_svc.bus import compact, decode, make_consumer, make_producer, send, setup_logging
from kafka_svc.course_logic import handle_request

log = logging.getLogger("worker")
ALLOWED_REPLY_TOPICS = {config.RESPONSE_TOPIC}


def process(store: dict, producer, consumer, msg) -> None:
    where = f"{msg.topic()} partition={msg.partition()} offset={msg.offset()}"
    request = decode(msg)
    if request is None:
        log.warning("received unreadable message from %s", where)
    else:
        log.info("received request from %s correlation_id=%s operation=%s message=%s",
                 where, request.get("correlation_id"), request.get("operation"), compact(request))

    response = handle_request(store, request)
    reply_to = request.get("reply_to") if request else None
    if reply_to not in ALLOWED_REPLY_TOPICS:
        log.warning("reply_to %r is not an allowed topic; replying on %s", reply_to, config.RESPONSE_TOPIC)
        reply_to = config.RESPONSE_TOPIC

    log.info("processed correlation_id=%s success=%s store_size=%d", response["correlation_id"], response["success"], len(store))
    log.info("sending response to %s correlation_id=%s message=%s", reply_to, response["correlation_id"], compact(response))
    partition, offset = send(producer, reply_to, response, key=response["correlation_id"])
    log.info("response acknowledged by the broker partition=%d offset=%d correlation_id=%s", partition, offset, response["correlation_id"])
    consumer.commit(message=msg, asynchronous=False)


def main() -> None:
    setup_logging()
    store: dict = {}
    stopping = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stopping.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stopping.update(flag=True))

    producer = make_producer(f"{config.PREFIX}-worker")
    consumer = make_consumer(config.WORKER_GROUP, f"{config.PREFIX}-worker")

    def on_assign(_consumer, partitions):
        log.info("Consumer is ready and listening on %s (group %s, partitions %s)",
                 config.REQUEST_TOPIC, config.WORKER_GROUP, [p.partition for p in partitions])

    consumer.subscribe([config.REQUEST_TOPIC], on_assign=on_assign)
    log.info("worker starting, bootstrap %s, entities held in a plain dict", config.BOOTSTRAP)
    try:
        while not stopping["flag"]:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                log.error("consumer error: %s", msg.error())
                continue
            try:
                process(store, producer, consumer, msg)
            except Exception:
                log.exception("failed to process offset %d; it stays uncommitted", msg.offset())
                raise
    finally:
        consumer.close()
        log.info("worker stopped")


if __name__ == "__main__":
    main()
