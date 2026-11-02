import json
import logging
import sys
import time
import uuid

from confluent_kafka import Consumer, KafkaException, Producer

from kafka_svc import config


class _UtcFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z"


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_UtcFormatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logging.basicConfig(level=level, handlers=[handler], force=True)


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def make_producer(client_id: str) -> Producer:
    return Producer({
        "bootstrap.servers": config.BOOTSTRAP,
        "client.id": client_id,
        "acks": "all",
        "enable.idempotence": True,
        "linger.ms": 0,
    })


def make_consumer(group_id: str, client_id: str, *, offset_reset: str = "earliest", auto_commit: bool = False) -> Consumer:
    conf = {
        "bootstrap.servers": config.BOOTSTRAP,
        "group.id": group_id,
        "client.id": client_id,
        "enable.auto.commit": auto_commit,
        "auto.offset.reset": offset_reset,
        "session.timeout.ms": 6000,
        "heartbeat.interval.ms": 2000,
    }
    if auto_commit:
        conf["auto.commit.interval.ms"] = 1000
    return Consumer(conf)


def send(producer: Producer, topic: str, value, key: str | None = None, headers: dict | None = None,
         partition: int | None = None, timeout: float = 10.0) -> tuple[int, int]:
    """Produces one message and waits for the broker acknowledgement; returns (partition, offset)."""
    payload = value if isinstance(value, bytes) else json.dumps(value).encode()
    outcome: dict = {}

    def delivered(err, msg):
        outcome["err"], outcome["msg"] = err, msg

    extra = {} if partition is None else {"partition": partition}
    producer.produce(topic, value=payload, key=key, headers=headers, on_delivery=delivered, **extra)
    producer.flush(timeout)
    if "msg" not in outcome:
        raise TimeoutError(f"no broker acknowledgement for {topic} within {timeout:g}s")
    if outcome["err"]:
        raise KafkaException(outcome["err"])
    return outcome["msg"].partition(), outcome["msg"].offset()


def decode(msg) -> dict | None:
    try:
        body = json.loads(msg.value())
    except (ValueError, TypeError):
        return None
    return body if isinstance(body, dict) else None


def compact(value) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def dead_letter(producer: Producer, msg, error: str, attempts: int) -> tuple[int, int]:
    from kafka_svc import config as cfg

    body = decode(msg)
    record = {
        "correlation_id": body.get("correlation_id") if body else (msg.key().decode("utf-8", "replace") if msg.key() else None),
        "source_topic": msg.topic(),
        "source_partition": msg.partition(),
        "source_offset": msg.offset(),
        "attempts": attempts,
        "error": error,
        "failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "original_value": (msg.value() or b"").decode("utf-8", errors="replace"),
    }
    return send(producer, cfg.DEAD_LETTER_TOPIC, record, key=record["correlation_id"] or f"{msg.topic()}-{msg.partition()}-{msg.offset()}")


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time() * 1000) % 1000:03d}Z"
