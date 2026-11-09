import logging
import threading
import time

from confluent_kafka import TopicPartition

from cache_svc import config
from kafka_svc import config as kafka_config
from kafka_svc.bus import compact, decode, make_consumer, make_producer, new_correlation_id, send, utc_now

log = logging.getLogger("agent_client")


class AgentClient:
    """Sends a question to the HW8 pipeline (s8360_inbox) and waits for the Reviewer's message on s8360_final."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._producer = make_producer("hw9-ingress")
        self._consumer = make_consumer(f"{kafka_config.PREFIX}_ingress_{new_correlation_id()[:8]}", "hw9-ingress", offset_reset="latest")
        meta = self._consumer.list_topics(kafka_config.FINAL_TOPIC, timeout=10).topics[kafka_config.FINAL_TOPIC]
        self._consumer.assign([TopicPartition(kafka_config.FINAL_TOPIC, p, self._consumer.get_watermark_offsets(
            TopicPartition(kafka_config.FINAL_TOPIC, p), timeout=10)[1]) for p in meta.partitions])

    def ask(self, question: str, timeout: float = config.AGENT_TIMEOUT_S) -> dict:
        with self._lock:
            correlation_id = new_correlation_id()
            message = {"correlation_id": correlation_id, "question": question, "submitted_at": utc_now()}
            log.info("sending question to %s correlation_id=%s message=%s", kafka_config.INBOX_TOPIC, correlation_id, compact(message))
            send(self._producer, kafka_config.INBOX_TOPIC, message, key=correlation_id)
            deadline = time.time() + timeout
            while time.time() < deadline:
                msg = self._consumer.poll(1.0)
                body = decode(msg) if msg is not None and not msg.error() else None
                if body and body.get("correlation_id") == correlation_id:
                    log.info("received final message from %s correlation_id=%s status=%s", kafka_config.FINAL_TOPIC, correlation_id, body.get("status"))
                    return body
            log.error("no final message for correlation_id=%s within %gs", correlation_id, timeout)
            return {"correlation_id": correlation_id, "status": "timeout", "answer": None, "question": question}

    def close(self) -> None:
        self._consumer.close()
