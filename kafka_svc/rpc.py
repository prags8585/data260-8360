import logging
import threading
import uuid
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout

from confluent_kafka import TopicPartition

from kafka_svc import config
from kafka_svc.bus import compact, decode, make_consumer, make_producer, new_correlation_id, send

log = logging.getLogger("client")


class KafkaRpcClient:
    """Sends a request to the request topic and waits for the response with the same correlation_id."""

    def __init__(self, client_id: str = f"{config.PREFIX}-client"):
        self.client_id = client_id
        self._producer = make_producer(client_id)
        self._consumer = make_consumer(f"{config.PREFIX}_client_{uuid.uuid4().hex[:8]}", client_id, offset_reset="latest")
        self._pending: dict[str, Future] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._pump, daemon=True, name=f"{client_id}-replies")

    def start(self) -> "KafkaRpcClient":
        # Assign explicitly at the current end of the response topic so a reply can never be missed.
        meta = self._consumer.list_topics(config.RESPONSE_TOPIC, timeout=10).topics[config.RESPONSE_TOPIC]
        assignment = []
        for partition in meta.partitions:
            _, high = self._consumer.get_watermark_offsets(TopicPartition(config.RESPONSE_TOPIC, partition), timeout=10)
            assignment.append(TopicPartition(config.RESPONSE_TOPIC, partition, high))
        self._consumer.assign(assignment)
        self._thread.start()
        return self

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)
        self._consumer.close()

    def _pump(self) -> None:
        while not self._stop.is_set():
            msg = self._consumer.poll(0.2)
            if msg is None or msg.error():
                continue
            body = decode(msg)
            future = self._pending.get(body.get("correlation_id")) if body else None
            if future is not None and not future.done():
                log.info("received response from %s correlation_id=%s success=%s message=%s",
                         config.RESPONSE_TOPIC, body["correlation_id"], body.get("success"), compact(body))
                future.set_result(body)

    def call(self, operation: str, data: dict, correlation_id: str | None = None, timeout: float = 10.0) -> dict:
        correlation_id = correlation_id or new_correlation_id()
        request = {"correlation_id": correlation_id, "reply_to": config.RESPONSE_TOPIC, "operation": operation, "data": data}
        future: Future = Future()
        self._pending[correlation_id] = future
        try:
            log.info("sending request to %s correlation_id=%s message=%s", config.REQUEST_TOPIC, correlation_id, compact(request))
            partition, offset = send(self._producer, config.REQUEST_TOPIC, request, key=correlation_id)
            log.info("request acknowledged by the broker partition=%d offset=%d correlation_id=%s", partition, offset, correlation_id)
            return future.result(timeout)
        except FutureTimeout:
            log.error("no response within %gs correlation_id=%s", timeout, correlation_id)
            return {"correlation_id": correlation_id, "success": False, "error": f"No response from worker within {timeout:g}s"}
        finally:
            self._pending.pop(correlation_id, None)
